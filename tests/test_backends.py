"""Testes unitários para backends.py — foco na lógica de seleção de agente do OpenCodeBackend."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backends import BackendResult, CrushBackend, OpenCodeBackend, _is_source_file, create_backend


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
#
# Lógica nova (2026-03-29): string matching substituído por regras estritas
# para eliminar falsos positivos (ex: "getCheckpoint" → terminal, "fix" → debug).
# Ver squire_feedback_session_2026-03-29.md.

class TestOpenCodeAgentSelection:

    # ── default: code ────────────────────────────────────────────────

    def test_default_retorna_code(self):
        """Título genérico sem erros → code."""
        assert backend._select_agent(hint("Implementar listagem de projetos")) == "code"

    def test_vazio_retorna_code(self):
        """dict vazio → code (default seguro)."""
        assert backend._select_agent({}) == "code"

    def test_titulo_fix_sem_erro_retorna_code(self):
        """'Fix' no título mas sem last_error e poucos attempts → code, não debug."""
        assert backend._select_agent(hint("Fix typo in comment", attempts=0)) == "code"

    def test_titulo_fix_com_poucos_attempts_retorna_code(self):
        """attempts=4 (abaixo de 6) sem last_error → code."""
        assert backend._select_agent(hint("Fix validation", attempts=4)) == "code"

    def test_titulo_check_em_meio_nao_e_terminal(self):
        """'getCheckpoint' contém 'check' mas não COMEÇA com verbo → code, não terminal.
        Regressão: substring matching antigo causava routing errado aqui."""
        assert backend._select_agent(hint("Implement getCheckpoint function")) == "code"

    def test_titulo_com_verbo_terminal_no_meio_e_code(self):
        """'add migrate command' — 'migrate' não está no início → code."""
        assert backend._select_agent(hint("add migrate command to CLI")) == "code"

    # ── debug: apenas com stack trace real ───────────────────────────

    def test_last_error_typeerror_retorna_debug(self):
        """'TypeError' em last_error contém marcador → debug."""
        assert backend._select_agent(hint(last_error="TypeError: cannot read property")) == "debug"

    def test_last_error_traceback_retorna_debug(self):
        """'Traceback' em last_error → debug."""
        assert backend._select_agent(hint(last_error="Traceback (most recent call last):")) == "debug"

    def test_last_error_assertionerror_retorna_debug(self):
        """'AssertionError' em last_error → debug."""
        assert backend._select_agent(hint("Fix login bug", last_error="AssertionError: expected True")) == "debug"

    def test_last_error_syntaxerror_retorna_debug(self):
        """'SyntaxError' em last_error → debug."""
        assert backend._select_agent(hint("Corrigir parser", last_error="SyntaxError: unexpected token")) == "debug"

    def test_last_error_cannot_find_retorna_debug(self):
        """'cannot find' em last_error (erro TS common) → debug."""
        assert backend._select_agent(hint(last_error="cannot find module './foo'")) == "debug"

    def test_last_error_is_not_defined_retorna_debug(self):
        """'is not defined' em last_error (ReferenceError JS) → debug."""
        assert backend._select_agent(hint(last_error="foo is not defined")) == "debug"

    def test_last_error_generico_sem_marcador_nao_e_debug(self):
        """'0 passed, 3 failed' não é stack trace → code (não debug)."""
        assert backend._select_agent(hint(last_error="0 passed, 3 failed")) == "code"

    def test_last_error_connection_refused_nao_e_debug(self):
        """'Connection refused' não contém marcadores de stack trace → não debug."""
        # Regressão: lógica anterior teria enviado para debug com qualquer last_error
        result = backend._select_agent(hint("Run migration script", last_error="Connection refused"))
        assert result != "debug"

    def test_6_attempts_sem_erro_retorna_debug(self):
        """attempts >= 6 sem last_error → debug (stuck sem erro explícito)."""
        assert backend._select_agent(hint("Qualquer coisa", attempts=6)) == "debug"

    def test_7_attempts_retorna_debug(self):
        """attempts=7 → debug."""
        assert backend._select_agent(hint("Outra task", attempts=7)) == "debug"

    def test_5_attempts_sem_erro_retorna_code(self):
        """attempts=5 (abaixo do threshold de 6) → code."""
        assert backend._select_agent(hint("Qualquer coisa", attempts=5)) == "code"

    def test_3_attempts_sem_erro_retorna_code(self):
        """attempts=3 → code (threshold é 6)."""
        assert backend._select_agent(hint("Adicionar endpoint", attempts=3)) == "code"

    # ── terminal: título COMEÇA com verbo operacional ─────────────────

    def test_run_retorna_terminal(self):
        """Título começando com 'run' → terminal."""
        assert backend._select_agent(hint("Run database migrations")) == "terminal"

    def test_migrate_retorna_terminal(self):
        """Título começando com 'migrate' → terminal."""
        assert backend._select_agent(hint("Migrate schema to v2")) == "terminal"

    def test_seed_retorna_terminal(self):
        """Título começando com 'seed' → terminal."""
        assert backend._select_agent(hint("Seed initial data")) == "terminal"

    def test_init_retorna_terminal(self):
        """Título começando com 'init' → terminal."""
        assert backend._select_agent(hint("Init project structure")) == "terminal"

    def test_deploy_retorna_terminal(self):
        """Título começando com 'deploy' → terminal."""
        assert backend._select_agent(hint("Deploy to staging")) == "terminal"

    def test_start_retorna_terminal(self):
        """Título começando com 'start' → terminal."""
        assert backend._select_agent(hint("Start development server")) == "terminal"

    def test_stop_retorna_terminal(self):
        """Título começando com 'stop' → terminal."""
        assert backend._select_agent(hint("Stop background workers")) == "terminal"

    def test_restart_retorna_terminal(self):
        """Título começando com 'restart' → terminal."""
        assert backend._select_agent(hint("Restart the queue processor")) == "terminal"

    def test_titulo_sem_verbo_exato_nao_e_terminal(self):
        """'Execute setup script' — 'execute' não está na lista → code."""
        assert backend._select_agent(hint("Execute setup script")) == "code"

    def test_titulo_verificar_nao_e_terminal(self):
        """'Verificar ambiente' — verbo PT não na lista → code."""
        assert backend._select_agent(hint("Verificar ambiente de desenvolvimento")) == "code"

    def test_descricao_banco_sem_verbo_no_titulo_nao_e_terminal(self):
        """Desc 'Inicializar banco' mas title="" → new logic usa só o title → code."""
        assert backend._select_agent(hint("", description="Inicializar banco de dados")) == "code"

    # ── build: título exatamente igual ao conjunto ────────────────────

    def test_scaffold_project_exato_retorna_build(self):
        """'scaffold project' (exato, em inglês) → build."""
        assert backend._select_agent(hint("scaffold project")) == "build"

    def test_setup_project_exato_retorna_build(self):
        """'setup project' (exato) → build."""
        assert backend._select_agent(hint("setup project")) == "build"

    def test_add_dockerfile_exato_retorna_build(self):
        """'add dockerfile' (exato) → build."""
        assert backend._select_agent(hint("add dockerfile")) == "build"

    def test_configure_ci_exato_retorna_build(self):
        """'configure ci' (exato) → build."""
        assert backend._select_agent(hint("configure ci")) == "build"

    def test_titulo_setup_em_pt_nao_e_build(self):
        """'Setup inicial do projeto' (PT, não exato) → code."""
        assert backend._select_agent(hint("Setup inicial do projeto")) == "code"

    def test_titulo_criar_dockerfile_nao_e_build(self):
        """'Criar Dockerfile para produção' (PT) → code."""
        assert backend._select_agent(hint("Criar Dockerfile para produção")) == "code"

    def test_titulo_scaffold_estrutura_nao_e_build(self):
        """'Scaffold estrutura do projeto' (não exato) → code."""
        assert backend._select_agent(hint("Scaffold estrutura do projeto")) == "code"

    # ── prioridade: debug > terminal > build ──────────────────────────

    def test_stack_trace_tem_prioridade_sobre_terminal(self):
        """Stack trace em last_error → debug, mesmo que título comece com 'run'."""
        result = backend._select_agent(hint("Run migration", last_error="TypeError: x is null"))
        assert result == "debug"

    def test_terminal_tem_prioridade_sobre_build(self):
        """'seed' no início → terminal, mesmo se tivesse match de build."""
        assert backend._select_agent(hint("seed and install dependencies")) == "terminal"

    def test_last_error_sem_marcador_nao_bloqueia_terminal(self):
        """last_error sem marcador de stack trace + título terminal → terminal."""
        result = backend._select_agent(hint("Run migration script", last_error="Connection refused"))
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

    def test_agent_used_code_para_titulo_setup_pt(self, tmp_path):
        """'Setup inicial do projeto com Dockerfile' (PT, não exato) → agent_used = 'code'.
        Regressão: lógica antiga retornava 'build' por substring matching."""
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

        assert result.agent_used == "code"

    def test_agent_used_build_para_titulo_exato(self, tmp_path):
        """'setup project' (exato) → agent_used = 'build'."""
        b = OpenCodeBackend(opencode_bin="opencode")
        task_hint = hint("setup project")

        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            result = b.execute_instruction(
                instruction="scaffold",
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


# ── TestAiderDeprecation ─────────────────────────────────────────────

class TestAiderDeprecation:
    """
    O backend 'aider' foi descontinuado em 2026-03-29 devido a falhas críticas
    (overwrite de tsconfig.json, artefatos .js, oscilação em 10 tentativas).
    create_backend('aider') deve levantar ValueError com mensagem clara.
    """

    def test_create_backend_aider_levanta_value_error(self):
        """create_backend('aider') deve levantar ValueError."""
        with pytest.raises(ValueError):
            create_backend("aider")

    def test_mensagem_deprecacao_menciona_alternativas(self):
        """Mensagem de erro deve mencionar 'opencode' ou 'litellm' como alternativas."""
        with pytest.raises(ValueError, match=r"opencode|litellm"):
            create_backend("aider")

    def test_mensagem_deprecacao_menciona_data(self):
        """Mensagem de erro deve mencionar a data de deprecação (2026-03-29)."""
        with pytest.raises(ValueError, match=r"2026-03-29"):
            create_backend("aider")

    def test_opencode_ainda_funciona(self):
        """create_backend('opencode') não deve levantar exceção."""
        backend_instance = create_backend("opencode")
        assert isinstance(backend_instance, OpenCodeBackend)

    def test_litellm_ainda_funciona(self):
        """create_backend('litellm') não deve levantar exceção."""
        from backends import LiteLLMBackend
        backend_instance = create_backend("litellm")
        assert isinstance(backend_instance, LiteLLMBackend)


# ── TestCrushBackend ──────────────────────────────────────────────────

class TestCrushBackend:
    """CrushBackend: execução via crush run, sem agentes, com strip de ANSI."""

    def _make_proc(self, returncode=0, stdout="done", stderr=""):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def _mock_lock(self):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    def test_agent_used_sempre_crush(self, tmp_path):
        """CrushBackend não roteia — agent_used deve ser sempre 'crush'."""
        b = CrushBackend(crush_bin="crush")
        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=["src/foo.ts"]):
            result = b.execute_instruction(
                instruction="faça algo",
                project_path=tmp_path,
                timeout=30,
            )
        assert result.agent_used == "crush"

    def test_agent_used_crush_com_task_hint(self, tmp_path):
        """task_hint não muda o agente — sempre 'crush'."""
        b = CrushBackend(crush_bin="crush")
        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            result = b.execute_instruction(
                instruction="corrija",
                project_path=tmp_path,
                timeout=30,
                task_hint={"title": "Run migration", "last_error": "TypeError: x is null"},
            )
        assert result.agent_used == "crush"

    def test_files_touched_via_git_diff(self, tmp_path):
        """files_touched vem de _git_diff_files."""
        b = CrushBackend(crush_bin="crush")
        expected = ["src/index.ts", "package.json"]
        with patch("backends.subprocess.run", return_value=self._make_proc()), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=expected):
            result = b.execute_instruction(
                instruction="qualquer",
                project_path=tmp_path,
                timeout=30,
            )
        assert result.files_touched == expected

    def test_ansi_removido_do_output(self, tmp_path):
        """Output com escape codes ANSI deve ser stripado."""
        ansi_output = "\x1b[32mDone!\x1b[0m  Modified 2 files."
        b = CrushBackend(crush_bin="crush")
        with patch("backends.subprocess.run", return_value=self._make_proc(stdout=ansi_output)), \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            result = b.execute_instruction(
                instruction="qualquer",
                project_path=tmp_path,
                timeout=30,
            )
        assert "\x1b" not in result.raw_output
        assert "Done!" in result.raw_output

    def test_instrucao_passada_via_stdin(self, tmp_path):
        """A instrução deve ser enviada como stdin (input=), não como argumento CLI."""
        b = CrushBackend(crush_bin="crush")
        with patch("backends.subprocess.run", return_value=self._make_proc()) as mock_run, \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            b.execute_instruction(
                instruction="instrução longa",
                project_path=tmp_path,
                timeout=30,
            )
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("input") == "instrução longa"
        # instrução não deve aparecer nos args do comando
        cmd_args = call_kwargs.args[0]
        assert "instrução longa" not in cmd_args

    def test_flags_obrigatorias_no_cmd(self, tmp_path):
        """--cwd, --quiet e --yolo devem sempre estar presentes no comando."""
        b = CrushBackend(crush_bin="crush")
        with patch("backends.subprocess.run", return_value=self._make_proc()) as mock_run, \
             patch("backends._LLMLock", return_value=self._mock_lock()), \
             patch.object(b, "_git_diff_files", return_value=[]):
            b.execute_instruction(
                instruction="qualquer",
                project_path=tmp_path,
                timeout=30,
            )
        cmd = mock_run.call_args.args[0]
        assert "--quiet" in cmd
        assert "--yolo" in cmd
        assert "--cwd" in cmd
        assert str(tmp_path) in cmd

    def test_erro_crush_nao_encontrado(self, tmp_path):
        """FileNotFoundError → BackendResult.error com mensagem clara."""
        b = CrushBackend(crush_bin="/nao/existe/crush")
        with patch("backends.subprocess.run", side_effect=FileNotFoundError()), \
             patch("backends._LLMLock", return_value=self._mock_lock()):
            result = b.execute_instruction(
                instruction="qualquer",
                project_path=tmp_path,
                timeout=30,
            )
        assert result.error is not None
        assert "crush not found" in result.error

    def test_timeout_retorna_erro(self, tmp_path):
        """TimeoutExpired → BackendResult.error mencionando timeout."""
        b = CrushBackend(crush_bin="crush")
        with patch("backends.subprocess.run", side_effect=subprocess.TimeoutExpired("crush", 30)), \
             patch("backends._LLMLock", return_value=self._mock_lock()):
            result = b.execute_instruction(
                instruction="qualquer",
                project_path=tmp_path,
                timeout=30,
            )
        assert result.error is not None
        assert "timed out" in result.error

    def test_create_backend_crush(self):
        """create_backend('crush') deve retornar instância de CrushBackend."""
        b = create_backend("crush")
        assert isinstance(b, CrushBackend)


# ── Mensagens de erro HTTP amigáveis ─────────────────────────────────

class TestFriendlyHTTPErrors:
    def _backend(self):
        from backends import LiteLLMBackend
        return LiteLLMBackend(model="meu-modelo", base_url="http://host:1234/v1", api_key="k")

    def _status_error(self, code: int):
        import httpx
        req = httpx.Request("POST", "http://host:1234/v1/chat/completions")
        resp = httpx.Response(code, request=req, text="detail")
        return httpx.HTTPStatusError("err", request=req, response=resp)

    def test_401_menciona_chave(self):
        import httpx
        b = self._backend()
        with patch.object(httpx.Client, "post", side_effect=self._status_error(401)):
            with pytest.raises(RuntimeError, match="SQUIRE_LITELLM_KEY"):
                b._call_api_with_retry("x", timeout=5)

    def test_404_menciona_modelo_e_endpoint(self):
        import httpx
        b = self._backend()
        with patch.object(httpx.Client, "post", side_effect=self._status_error(404)):
            with pytest.raises(RuntimeError, match="meu-modelo.*host:1234"):
                b._call_api_with_retry("x", timeout=5)

    def test_connect_error_menciona_endpoint(self):
        import httpx
        b = self._backend()
        with (
            patch.object(httpx.Client, "post", side_effect=httpx.ConnectError("refused")),
            patch("backends.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="inacessível.*host:1234"):
                b._call_api_with_retry("x", timeout=5)
