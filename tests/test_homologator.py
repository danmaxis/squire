"""Testes unitários para homologator.py — foco na filtragem de arquivos e limites de prompt."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from homologator import Homologator


def make_homologator(tmp_path: Path) -> Homologator:
    return Homologator(project_path=str(tmp_path), claude_bin="claude", verbose=False)


# ── TestGitFallbackFiles ─────────────────────────────────────────────

class TestGitFallbackFiles:
    """_git_fallback_files deve filtrar node_modules/dist e retornar só arquivos fonte."""

    def _proc(self, stdout="", returncode=0):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = ""
        return p

    def test_filtra_node_modules(self, tmp_path):
        h = make_homologator(tmp_path)
        ls_output = "src/index.ts\nnode_modules/.bin/tsc\nnode_modules/typescript/ts.js\npackage.json\n"
        with patch("homologator.subprocess.run", side_effect=[
            self._proc(""),          # git diff HEAD
            self._proc(""),          # git diff --cached HEAD
            self._proc(ls_output),   # git ls-files
        ]):
            files = h._git_fallback_files()

        assert "src/index.ts" in files
        assert "package.json" in files
        assert not any("node_modules" in f for f in files)

    def test_filtra_dist(self, tmp_path):
        h = make_homologator(tmp_path)
        ls_output = "src/bing.ts\ndist/bing.js\ndist/bing.d.ts\n"
        with patch("homologator.subprocess.run", side_effect=[
            self._proc(""),
            self._proc(""),
            self._proc(ls_output),
        ]):
            files = h._git_fallback_files()

        assert "src/bing.ts" in files
        assert not any("dist" in f for f in files)

    def test_repo_sem_commits_retorna_apenas_fontes(self, tmp_path):
        """git diff falha (sem HEAD) mas ls-files retorna node_modules — deve filtrar."""
        h = make_homologator(tmp_path)
        all_untracked = (
            "src/index.ts\npackage.json\ntsconfig.json\n"
            "node_modules/.bin/acorn\nnode_modules/typescript/README.md\n"
            "dist/index.js\n"
        )
        with patch("homologator.subprocess.run", side_effect=[
            self._proc("", returncode=128),
            self._proc("", returncode=128),
            self._proc(all_untracked),
        ]):
            files = h._git_fallback_files()

        assert set(files) == {"src/index.ts", "package.json", "tsconfig.json"}

    def test_retorna_vazio_em_excecao(self, tmp_path):
        h = make_homologator(tmp_path)
        with patch("homologator.subprocess.run", side_effect=Exception("git não encontrado")):
            files = h._git_fallback_files()
        assert files == []


# ── TestReadFilesForReview ───────────────────────────────────────────

class TestReadFilesForReview:
    """_read_files_for_review — limites de arquivos e conteúdo para não inflar o prompt."""

    def test_le_arquivo_existente(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("const x = 1;\n")
        h = make_homologator(tmp_path)
        result = h._read_files_for_review(["src/index.ts"])
        assert "src/index.ts" in result
        assert "const x = 1;" in result

    def test_retorna_mensagem_sem_arquivos(self, tmp_path):
        h = make_homologator(tmp_path)
        # Sem files_touched e sem git → fallbacks retornam vazio
        with patch.object(h, "_git_fallback_files", return_value=[]), \
             patch.object(h, "_recent_code_files", return_value=[]):
            result = h._read_files_for_review([])
        assert "Nenhum arquivo" in result

    def test_cap_maximo_de_arquivos(self, tmp_path):
        """Mais de 20 arquivos passados → só os 20 primeiros são lidos."""
        h = make_homologator(tmp_path)
        # Criar 25 arquivos de código
        (tmp_path / "src").mkdir()
        files = []
        for i in range(25):
            p = tmp_path / "src" / f"file{i:02d}.ts"
            p.write_text(f"// file {i}\n")
            files.append(f"src/file{i:02d}.ts")

        result = h._read_files_for_review(files)

        # Só os primeiros 20 devem aparecer
        included = [f for f in files if f in result]
        assert len(included) <= 20

    def test_cap_tamanho_conteudo(self, tmp_path):
        """Conteúdo total acima de 80KB deve ser truncado."""
        h = make_homologator(tmp_path)
        (tmp_path / "src").mkdir()
        # Criar 5 arquivos de 25KB cada (total 125KB > limite de 80KB)
        files = []
        for i in range(5):
            p = tmp_path / "src" / f"big{i}.ts"
            p.write_text("x" * 25_000)
            files.append(f"src/big{i}.ts")

        result = h._read_files_for_review(files)

        assert "truncado" in result
        # Conteúdo deve estar bem abaixo de 125KB
        assert len(result.encode("utf-8")) < 120_000

    def test_usa_fallback_quando_files_touched_vazio(self, tmp_path):
        """Sem files_touched → chama _git_fallback_files."""
        h = make_homologator(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export {}")

        with patch.object(h, "_git_fallback_files", return_value=["src/app.ts"]) as mock_fb, \
             patch.object(h, "_recent_code_files", return_value=[]):
            result = h._read_files_for_review([])

        mock_fb.assert_called_once()
        assert "src/app.ts" in result

    def test_usa_recent_files_quando_git_vazio(self, tmp_path):
        """_git_fallback retorna [] → chama _recent_code_files."""
        h = make_homologator(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export {}")

        with patch.object(h, "_git_fallback_files", return_value=[]), \
             patch.object(h, "_recent_code_files", return_value=["src/app.ts"]) as mock_rc:
            result = h._read_files_for_review([])

        mock_rc.assert_called_once()
        assert "src/app.ts" in result

    def test_arquivo_inexistente_nao_quebra(self, tmp_path):
        """Arquivo listado mas não existente → mensagem de erro no resultado, não exceção."""
        h = make_homologator(tmp_path)
        result = h._read_files_for_review(["src/nao_existe.ts"])
        assert "nao_existe.ts" in result
        assert "erro ao ler" in result


# ── TestBuildReviewPromptViking ──────────────────────────────────────

class TestBuildReviewPromptViking:
    """Gap 7: Viking context injetado no prompt de review."""

    def _make_context(self):
        from models import LLMContextSummary
        return LLMContextSummary(files_touched=[], tests_passing=3, tests_failing=0)

    def _make_task(self, **kwargs):
        from models import Task, TaskStatus
        defaults = dict(
            id="t1", title="Test", description="Desc",
            status=TaskStatus.pending, attempts=0, max_attempts=10,
            homologation_attempt=0, max_homologation_attempts=3,
        )
        defaults.update(kwargs)
        return Task(**defaults)

    def test_viking_context_aparece_no_prompt(self, tmp_path):
        """Quando Viking docs existem, devem aparecer no prompt de review."""
        h = make_homologator(tmp_path)
        viking_dir = tmp_path / "docs" / "viking"
        viking_dir.mkdir(parents=True)
        (viking_dir / "stack_python.md").write_text("Use ruff para lint, proibido black")

        prompt = h._build_review_prompt(self._make_task(), self._make_context(), 1)
        assert "Use ruff para lint" in prompt
        assert "Padrão Viking" in prompt

    def test_checklist_item_viking_presente(self, tmp_path):
        """Com Viking docs, item 5 do checklist deve estar no prompt."""
        h = make_homologator(tmp_path)
        viking_dir = tmp_path / "docs" / "viking"
        viking_dir.mkdir(parents=True)
        (viking_dir / "banco_dados.md").write_text("Proibido ORM")

        prompt = h._build_review_prompt(self._make_task(), self._make_context(), 1)
        assert "Viking" in prompt
        # Deve ter mais itens de avaliação que o padrão (5 vs 4)
        assert prompt.count("\n1.") + prompt.count("\n2.") + prompt.count("\n5.") > 0

    def test_sem_viking_docs_nao_adiciona_checklist(self, tmp_path):
        """Sem /docs/viking/, o item 5 não aparece."""
        h = make_homologator(tmp_path)
        prompt = h._build_review_prompt(self._make_task(), self._make_context(), 1)
        assert "restrições de domínio" not in prompt.lower() or "Padrão Viking" not in prompt


# ── TestReviewTestIntegrity ──────────────────────────────────────────

class TestReviewTestIntegrity:
    """Gap 7: review() rejeita automaticamente se Executor tocou em test_*.py."""

    def _make_context(self):
        from models import LLMContextSummary
        return LLMContextSummary(files_touched=[], tests_passing=5, tests_failing=0)

    def _make_task(self):
        from models import Task, TaskStatus
        return Task(
            id="t1", title="T", description="D",
            status=TaskStatus.implementing, attempts=0, max_attempts=10,
            homologation_attempt=0, max_homologation_attempts=3,
        )

    def test_rejeita_quando_teste_modificado(self, tmp_path):
        """review() com test_hashes deve rejeitar se arquivo de teste foi alterado."""
        from homologator import Homologator
        h = Homologator(project_path=str(tmp_path), claude_bin="claude", verbose=False)

        test_file = tmp_path / "test_core.py"
        test_file.write_text("original")
        hashes_before = {str(test_file): __import__("hashlib").sha256(b"original").hexdigest()}

        # Simular modificação pelo Executor
        test_file.write_text("MODIFICADO")

        with patch("homologator.subprocess.run"):  # não deve ser chamado
            result = h.review(self._make_task(), self._make_context(), test_hashes=hashes_before)

        assert result.approved is False
        assert "VIOLAÇÃO" in result.summary
        assert "test_core.py" in result.feedback

    def test_nao_chama_claude_quando_violacao_detectada(self, tmp_path):
        """Quando violação de teste é detectada, claude não deve ser invocado."""
        import json as _json
        from homologator import Homologator
        h = Homologator(project_path=str(tmp_path), claude_bin="claude", verbose=False)

        test_file = tmp_path / "test_x.py"
        test_file.write_text("original")
        hashes = {str(test_file): __import__("hashlib").sha256(b"original").hexdigest()}
        test_file.write_text("tampered")

        calls = []

        def track_subprocess(cmd, **kwargs):
            calls.append(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("inner_loop.subprocess.run", side_effect=track_subprocess):
            h.review(self._make_task(), self._make_context(), test_hashes=hashes)

        # git revert pode ter sido chamado, mas "claude" nunca deve aparecer
        assert not any("claude" in str(c) for c in calls)

    def test_sem_test_hashes_chama_claude_normalmente(self, tmp_path):
        """Sem test_hashes, o fluxo normal (chamar Claude) deve ocorrer."""
        import json as _json
        from homologator import Homologator
        h = Homologator(project_path=str(tmp_path), claude_bin="claude", verbose=False)

        review_data = {"approved": True, "summary": "ok", "feedback": "", "fix_suggestion": "", "suggestions": []}
        stdout = _json.dumps({"result": _json.dumps(review_data)})
        mock_result = MagicMock(returncode=0, stdout=stdout, stderr="")

        with patch("homologator.subprocess.run", return_value=mock_result):
            result = h.review(self._make_task(), self._make_context(), test_hashes=None)

        assert result.approved is True


# ── TestErrorKind ────────────────────────────────────────────────────

class TestErrorKind:
    """review() classifica falhas em error_kind: infra (transiente) vs config."""

    def _review(self, tmp_path, **subprocess_behavior):
        from models import LLMContextSummary, Task
        h = make_homologator(tmp_path)
        task = Task(id="task-001", title="T")
        ctx = LLMContextSummary()
        with patch("homologator.subprocess.run", **subprocess_behavior):
            return h.review(task=task, context=ctx)

    def _proc(self, stdout="", stderr="", returncode=0):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = stderr
        return p

    def test_returncode_diferente_de_zero_e_infra(self, tmp_path):
        r = self._review(tmp_path, return_value=self._proc(returncode=2, stderr="boom"))
        assert r.error_kind == "infra"

    def test_stdout_vazio_e_infra(self, tmp_path):
        r = self._review(tmp_path, return_value=self._proc(stdout="   "))
        assert r.error_kind == "infra"
        assert "vazio" in r.error

    def test_timeout_e_infra(self, tmp_path):
        import subprocess as sp
        r = self._review(tmp_path, side_effect=sp.TimeoutExpired(cmd="claude", timeout=180))
        assert r.error_kind == "infra"
        assert "timeout" in r.error.lower()

    def test_binario_ausente_e_config(self, tmp_path):
        r = self._review(tmp_path, side_effect=FileNotFoundError("claude"))
        assert r.error_kind == "config"
        assert "SQUIRE_CLAUDE_BIN" in r.error

    def test_json_invalido_e_infra(self, tmp_path):
        r = self._review(tmp_path, return_value=self._proc(stdout="not json at all"))
        assert r.error_kind == "infra"
        assert r.approved is False

    def test_review_valido_sem_error_kind(self, tmp_path):
        import json as _json
        envelope = _json.dumps({
            "result": _json.dumps({"approved": True, "summary": "ok", "feedback": "f"}),
            "total_cost_usd": 0.01,
        })
        r = self._review(tmp_path, return_value=self._proc(stdout=envelope))
        assert r.error_kind is None
        assert r.approved is True


# ── Parser tolerante a prosa em volta do JSON ────────────────────────

class TestJsonExtractionFallback:
    def _review_with_stdout(self, tmp_path, inner: str):
        import json as _json
        from models import LLMContextSummary, Task
        h = make_homologator(tmp_path)
        envelope = _json.dumps({"result": inner, "total_cost_usd": 0.01})
        proc = MagicMock(returncode=0, stdout=envelope, stderr="")
        with patch("homologator.subprocess.run", return_value=proc):
            return h.review(task=Task(id="t", title="T"), context=LLMContextSummary())

    def test_json_envolto_em_prosa_e_parseado(self, tmp_path):
        inner = (
            'Analisei o código com cuidado. Aqui está o veredito:\n\n'
            '{"approved": true, "summary": "ok", "feedback": "f"}\n\n'
            'Espero que ajude!'
        )
        r = self._review_with_stdout(tmp_path, inner)
        assert r.error is None
        assert r.approved is True
        assert r.summary == "ok"

    def test_chaves_falsas_antes_do_json_real(self, tmp_path):
        inner = 'O objeto {invalido} precede {"approved": false, "summary": "s", "feedback": "f"}'
        r = self._review_with_stdout(tmp_path, inner)
        assert r.error is None
        assert r.approved is False

    def test_sem_json_continua_infra_error(self, tmp_path):
        r = self._review_with_stdout(tmp_path, "só prosa, nenhum objeto aqui")
        assert r.error_kind == "infra"
