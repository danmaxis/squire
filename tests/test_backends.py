"""Testes unitários para backends.py — foco na lógica de seleção de agente do OpenCodeBackend."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backends import BackendResult, OpenCodeBackend, _is_source_file


# ── Helpers ──────────────────────────────────────────────────────────

def hint(
    title: str = "",
    description: str = "",
    attempts: int = 0,
    last_error: str | None = None,
    skip_homologation: bool = False,
) -> dict:
    return {
        "title": title,
        "description": description,
        "attempts": attempts,
        "last_error": last_error,
        "skip_homologation": skip_homologation,
    }


backend = OpenCodeBackend.__new__(OpenCodeBackend)  # instância sem __init__


# ── TestOpenCodeAgentSelection ────────────────────────────────────────

class TestOpenCodeAgentSelection:

    def test_default_retorna_code(self):
        assert backend._select_agent(hint("Implementar listagem de projetos")) == "code"

    def test_vazio_retorna_code(self):
        assert backend._select_agent({}) == "code"

    # ── debug ─────────────────────────────────────────────────────────

    def test_com_last_error_retorna_debug(self):
        assert backend._select_agent(hint(last_error="TypeError: cannot read property")) == "debug"

    def test_stuck_3_tentativas_retorna_debug(self):
        assert backend._select_agent(hint("Adicionar endpoint", attempts=3)) == "debug"

    def test_stuck_5_tentativas_retorna_debug(self):
        assert backend._select_agent(hint("Qualquer coisa", attempts=5)) == "debug"

    def test_titulo_fix_com_erro_retorna_debug(self):
        assert backend._select_agent(hint("Fix login bug", last_error="AssertionError")) == "debug"

    def test_titulo_corrigir_com_erro_retorna_debug(self):
        assert backend._select_agent(hint("Corrigir falha no parser", last_error="SyntaxError")) == "debug"

    def test_titulo_fix_sem_erro_sem_tentativas_nao_retorna_debug(self):
        # Fix no título mas sem erro e poucos attempts → code (não garante debug sem contexto)
        result = backend._select_agent(hint("Fix typo in comment", attempts=0))
        assert result == "code"

    def test_titulo_fix_com_muitas_tentativas_retorna_debug(self):
        assert backend._select_agent(hint("Fix validation", attempts=4)) == "debug"

    # ── terminal ──────────────────────────────────────────────────────

    def test_keyword_migration_retorna_terminal(self):
        assert backend._select_agent(hint("Run database migrations")) == "terminal"

    def test_keyword_seed_retorna_terminal(self):
        assert backend._select_agent(hint("Seed initial data")) == "terminal"

    def test_keyword_script_retorna_terminal(self):
        assert backend._select_agent(hint("Execute setup script")) == "terminal"

    def test_keyword_ambiente_retorna_terminal(self):
        assert backend._select_agent(hint("Verificar ambiente de desenvolvimento")) == "terminal"

    def test_keyword_banco_retorna_terminal(self):
        assert backend._select_agent(hint("", description="Inicializar banco de dados")) == "terminal"

    # ── build ─────────────────────────────────────────────────────────

    def test_keyword_setup_retorna_build(self):
        assert backend._select_agent(hint("Setup inicial do projeto")) == "build"

    def test_keyword_dockerfile_retorna_build(self):
        assert backend._select_agent(hint("Criar Dockerfile para produção")) == "build"

    def test_keyword_scaffold_retorna_build(self):
        assert backend._select_agent(hint("Scaffold estrutura do projeto")) == "build"

    def test_keyword_tsconfig_retorna_build(self):
        assert backend._select_agent(hint("", description="Configurar tsconfig.json")) == "build"

    def test_keyword_boilerplate_retorna_build(self):
        assert backend._select_agent(hint("Criar boilerplate Next.js")) == "build"

    # ── plan ──────────────────────────────────────────────────────────

    def test_skip_homolog_com_design_retorna_plan(self):
        assert backend._select_agent(hint("Design da arquitetura de módulos", skip_homologation=True)) == "plan"

    def test_skip_homolog_com_arquitetura_retorna_plan(self):
        assert backend._select_agent(hint("Definir arquitetura do sistema", skip_homologation=True)) == "plan"

    def test_skip_homolog_sem_keyword_design_nao_retorna_plan(self):
        # skip_homolog mas sem keyword de design → code (não é um plano, é só boilerplate simples)
        result = backend._select_agent(hint("Criar arquivo README", skip_homologation=True))
        assert result != "plan"

    def test_design_sem_skip_homolog_nao_retorna_plan(self):
        # Keyword de design mas sem skip_homologation → code (será homologado normalmente)
        result = backend._select_agent(hint("Design da API"))
        assert result != "plan"

    # ── prioridade de regras ───────────────────────────────────────────

    def test_erro_tem_prioridade_sobre_terminal(self):
        # Tem keyword de terminal mas tem last_error → debug ganha
        result = backend._select_agent(hint("Run migration script", last_error="Connection refused"))
        assert result == "debug"

    def test_erro_tem_prioridade_sobre_build(self):
        result = backend._select_agent(hint("Setup projeto", last_error="npm ERR!"))
        assert result == "debug"

    def test_terminal_tem_prioridade_sobre_build(self):
        # Ambos: seed (terminal) e install (build) → terminal ganha primeiro
        result = backend._select_agent(hint("Seed and install dependencies"))
        assert result == "terminal"


# ── TestBackendResult ────────────────────────────────────────────────

class TestOpenCodeBackendAgentUsed:
    """execute_instruction deve popular BackendResult.agent_used com o agente selecionado."""

    def _make_proc(self, returncode=0, stdout="done", stderr=""):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def _git_proc(self):
        p = MagicMock()
        p.stdout = ""
        p.returncode = 0
        return p

    def _mock_lock(self):
        """Context manager mock para _LLMLock (evita tentar criar /mnt/user)."""
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    def test_agent_used_preenchido_no_resultado(self, tmp_path):
        """BackendResult.agent_used deve refletir o agente escolhido por _select_agent."""
        b = OpenCodeBackend(opencode_bin="opencode")
        task_hint = hint("Implementar feature X")  # → code

        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=["src/foo.ts"]):
            result = b.execute_instruction(
                instruction="faça algo",
                project_path=tmp_path,
                timeout=30,
                task_hint=task_hint,
            )

        assert result.agent_used == "code"

    def test_agent_used_debug_quando_ha_erro(self, tmp_path):
        b = OpenCodeBackend(opencode_bin="opencode")
        task_hint = hint("Qualquer task", last_error="TypeError: x is undefined")

        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            result = b.execute_instruction(
                instruction="corrija",
                project_path=tmp_path,
                timeout=30,
                task_hint=task_hint,
            )

        assert result.agent_used == "debug"

    def test_agent_used_build_keyword(self, tmp_path):
        b = OpenCodeBackend(opencode_bin="opencode")
        task_hint = hint("Setup inicial do projeto com Dockerfile")

        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            result = b.execute_instruction(
                instruction="inicializar",
                project_path=tmp_path,
                timeout=30,
                task_hint=task_hint,
            )

        assert result.agent_used == "build"

    def test_agent_used_vazio_sem_task_hint(self, tmp_path):
        """Sem task_hint → agente padrão (code), agent_used deve ser preenchido."""
        b = OpenCodeBackend(opencode_bin="opencode")

        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            result = b.execute_instruction(
                instruction="qualquer",
                project_path=tmp_path,
                timeout=30,
            )

        assert result.agent_used == "code"  # default


# ── TestIsSourceFile ─────────────────────────────────────────────────

class TestIsSourceFile:
    """_is_source_file — garante que node_modules/dist são excluídos do files_touched."""

    # ── arquivos que DEVEM passar ────────────────────────────────────

    def test_ts_source(self):
        assert _is_source_file("src/index.ts") is True

    def test_tsx_source(self):
        assert _is_source_file("src/components/Card.tsx") is True

    def test_py_source(self):
        assert _is_source_file("squire.py") is True

    def test_json_config(self):
        assert _is_source_file("package.json") is True

    def test_tsconfig(self):
        assert _is_source_file("tsconfig.json") is True

    def test_gitignore(self):
        assert _is_source_file(".gitignore") is True

    def test_dockerfile(self):
        assert _is_source_file("Dockerfile") is True

    def test_yaml(self):
        assert _is_source_file("docker-compose.yml") is True

    def test_nested_source(self):
        assert _is_source_file("src/lib/utils.ts") is True

    # ── arquivos que NÃO devem passar ────────────────────────────────

    def test_node_modules_binary(self):
        assert _is_source_file("node_modules/.bin/tsc") is False

    def test_node_modules_package(self):
        assert _is_source_file("node_modules/typescript/lib/typescript.js") is False

    def test_node_modules_deeply_nested(self):
        assert _is_source_file("node_modules/@cspotcode/source-map-support/LICENSE.md") is False

    def test_dist_js(self):
        assert _is_source_file("dist/index.js") is False

    def test_dist_dts(self):
        assert _is_source_file("dist/bing.d.ts") is False

    def test_build_output(self):
        assert _is_source_file("build/app.js") is False

    def test_next_cache(self):
        assert _is_source_file(".next/server/app/page.js") is False

    def test_pycache(self):
        assert _is_source_file("__pycache__/squire.cpython-311.pyc") is False

    def test_venv(self):
        assert _is_source_file(".venv/lib/python3.11/site-packages/pydantic/__init__.py") is False


# ── TestGitDiffFilesFilter ───────────────────────────────────────────

class TestGitDiffFilesFilter:
    """_git_diff_files — node_modules/dist devem ser filtrados do resultado."""

    def _make_proc(self, stdout="", returncode=0):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = ""
        return p

    def test_filtra_node_modules(self, tmp_path):
        b = OpenCodeBackend(opencode_bin="opencode")
        # OpenCodeBackend._git_diff_files faz 2 chamadas: git diff HEAD + git ls-files
        ls_output = "src/index.ts\nnode_modules/.bin/tsc\nnode_modules/typescript/lib/ts.js\npackage.json\n"
        with patch("backends.subprocess.run", side_effect=[
            self._make_proc(""),          # git diff HEAD
            self._make_proc(ls_output),   # git ls-files
        ]):
            files = b._git_diff_files(tmp_path)

        assert "src/index.ts" in files
        assert "package.json" in files
        assert not any("node_modules" in f for f in files)

    def test_filtra_dist(self, tmp_path):
        b = OpenCodeBackend(opencode_bin="opencode")
        ls_output = "src/bing.ts\ndist/bing.js\ndist/bing.d.ts\n"
        with patch("backends.subprocess.run", side_effect=[
            self._make_proc(""),
            self._make_proc(ls_output),
        ]):
            files = b._git_diff_files(tmp_path)

        assert "src/bing.ts" in files
        assert not any("dist" in f for f in files)

    def test_sem_commits_retorna_apenas_fontes(self, tmp_path):
        """Repo sem HEAD: git diff falha (returncode 128), ls-files retorna todos os untracked."""
        b = OpenCodeBackend(opencode_bin="opencode")
        all_untracked = (
            "src/index.ts\npackage.json\ntsconfig.json\n"
            "node_modules/.bin/acorn\nnode_modules/typescript/README.md\n"
            "dist/index.js\n"
        )
        with patch("backends.subprocess.run", side_effect=[
            self._make_proc("", returncode=128),   # git diff HEAD falha
            self._make_proc(all_untracked),         # git ls-files
        ]):
            files = b._git_diff_files(tmp_path)

        assert set(files) == {"src/index.ts", "package.json", "tsconfig.json"}
