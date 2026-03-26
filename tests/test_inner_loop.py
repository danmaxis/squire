"""Testes unitários para o InnerLoop."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backends import BackendResult
from inner_loop import InnerLoop, InnerLoopResult
from models import LLMContextSummary, Task, TaskStatus


def make_task(**kwargs) -> Task:
    defaults = dict(id="task-001", title="Test task", description="Do something",
                    status=TaskStatus.pending, attempts=0, max_attempts=10,
                    homologation_attempt=0, max_homologation_attempts=3)
    defaults.update(kwargs)
    return Task(**defaults)


def make_inner_loop(tmp_path: Path, backend_result: BackendResult | None = None,
                    test_success: bool = True, verbose: bool = False) -> InnerLoop:
    """Cria InnerLoop com backend mockado."""
    mock_backend = MagicMock()
    mock_backend.execute_instruction.return_value = backend_result or BackendResult(
        files_touched=["src/foo.ts"],
        raw_output="const x = 1;",
    )

    il = InnerLoop(str(tmp_path), backend=mock_backend, verbose=verbose)

    # Mock _run_tests para controlar resultado
    il._run_tests = MagicMock(return_value={
        "success": test_success,
        "passing": 1 if test_success else 0,
        "failing": 0 if test_success else 1,
        "output": "ok" if test_success else "FAIL",
        "lint_clean": True,
        "skipped": False,
    })
    return il


class TestExecute:
    def test_retorna_sucesso_quando_testes_passam(self, tmp_path):
        il = make_inner_loop(tmp_path, test_success=True)
        result = il.execute(make_task())
        assert result.success is True
        assert result.files_touched == ["src/foo.ts"]
        assert result.error is None

    def test_retorna_falha_quando_testes_falham(self, tmp_path):
        il = make_inner_loop(tmp_path, test_success=False)
        result = il.execute(make_task())
        assert result.success is False
        assert result.tests_failing == 1

    def test_propaga_erro_do_backend(self, tmp_path):
        backend_result = BackendResult(error="LLM call failed: 500")
        il = make_inner_loop(tmp_path, backend_result=backend_result)
        result = il.execute(make_task())
        assert result.error == "LLM call failed: 500"
        assert result.success is False

    def test_context_summary_preenchido(self, tmp_path):
        il = make_inner_loop(tmp_path, test_success=True)
        result = il.execute(make_task())
        assert result.context_summary is not None
        assert result.context_summary.files_touched == ["src/foo.ts"]

    def test_sem_testes_configurados(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.execute_instruction.return_value = BackendResult(
            files_touched=["src/foo.ts"], raw_output=""
        )
        il = InnerLoop(str(tmp_path), backend=mock_backend, verbose=False)
        il._run_tests = MagicMock(return_value={
            "success": True, "passing": 0, "failing": 0,
            "output": "No test script", "lint_clean": True, "skipped": True,
        })
        result = il.execute(make_task())
        assert result.success is True
        assert result.tests_skipped is True


class TestBuildInstruction:
    def test_inclui_titulo_e_descricao(self, tmp_path):
        il = InnerLoop(str(tmp_path), verbose=False)
        task = make_task(title="My Task", description="Do the thing")
        instr = il._build_instruction(task, None, "")
        assert "My Task" in instr
        assert "Do the thing" in instr

    def test_inclui_erro_do_contexto_anterior(self, tmp_path):
        il = InnerLoop(str(tmp_path), verbose=False)
        ctx = LLMContextSummary(last_error="TypeError: foo is not a function",
                                files_touched=["src/a.ts"])
        instr = il._build_instruction(make_task(), ctx, "")
        assert "TypeError: foo is not a function" in instr

    def test_inclui_extra_instructions(self, tmp_path):
        il = InnerLoop(str(tmp_path), verbose=False)
        instr = il._build_instruction(make_task(), None, "Use only React hooks")
        assert "Use only React hooks" in instr

    def test_inclui_subtasks(self, tmp_path):
        from models import Subtask
        il = InnerLoop(str(tmp_path), verbose=False)
        task = make_task()
        task.subtasks = [Subtask(id="s1", title="Sub 1"), Subtask(id="s2", title="Sub 2")]
        instr = il._build_instruction(task, None, "")
        assert "Sub 1" in instr
        assert "Sub 2" in instr

    def test_sem_contexto_anterior_nao_inclui_secao_erro(self, tmp_path):
        il = InnerLoop(str(tmp_path), verbose=False)
        instr = il._build_instruction(make_task(), None, "")
        assert "Erro da tentativa anterior" not in instr


class TestRunTests:
    def test_pula_sem_package_json(self, tmp_path):
        il = InnerLoop(str(tmp_path), verbose=False)
        result = il._run_tests()
        assert result["success"] is True
        assert result["skipped"] is True

    def test_pula_sem_script_test_no_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {}}')
        il = InnerLoop(str(tmp_path), verbose=False)
        result = il._run_tests()
        assert result["success"] is True
        assert result["skipped"] is True

    def test_detecta_script_test(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
        il = InnerLoop(str(tmp_path), verbose=False)
        assert il._has_npm_test_script() is True

    def test_nao_detecta_sem_script(self, tmp_path):
        (tmp_path / "package.json").write_text('{"scripts": {"build": "next build"}}')
        il = InnerLoop(str(tmp_path), verbose=False)
        assert il._has_npm_test_script() is False


class TestRunSyntaxCheck:
    """_run_syntax_check — Bug 3: não penalizar quando tsc local não está instalado."""

    def test_pula_ts_sem_node_modules_tsc(self, tmp_path):
        """tsconfig.json existe mas node_modules/.bin/tsc ausente → retorna None."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        il = InnerLoop(str(tmp_path), verbose=False)
        result = il._run_syntax_check()
        assert result is None

    def test_pula_ts_sem_tsconfig(self, tmp_path):
        """Sem tsconfig.json → não tenta checagem TypeScript → retorna None."""
        il = InnerLoop(str(tmp_path), verbose=False)
        result = il._run_syntax_check()
        assert result is None

    def test_ts_erro_sintaxe_com_tsc_local(self, tmp_path):
        """Com tsc local instalado e erro de sintaxe → retorna dict de falha."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        tsc_bin = tmp_path / "node_modules" / ".bin"
        tsc_bin.mkdir(parents=True)
        (tsc_bin / "tsc").touch()

        il = InnerLoop(str(tmp_path), verbose=False)
        with patch("inner_loop.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="error TS1005", stderr="")
            result = il._run_syntax_check()

        assert result is not None
        assert result["success"] is False
        assert "TypeScript" in result["output"]

    def test_ts_ok_com_tsc_local(self, tmp_path):
        """Com tsc local instalado e sintaxe ok → retorna None."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        tsc_bin = tmp_path / "node_modules" / ".bin"
        tsc_bin.mkdir(parents=True)
        (tsc_bin / "tsc").touch()

        il = InnerLoop(str(tmp_path), verbose=False)
        with patch("inner_loop.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = il._run_syntax_check()

        assert result is None
