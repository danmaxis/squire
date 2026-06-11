"""Testes do agente host (agent_cli.py) — fila, validação, execução."""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agent_cli
from models import CommandResult, CommandStatus, CommandType, QueuedCommand


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def queue(tmp_path, monkeypatch):
    """STATE_ROOT temporário com a fila criada e um projeto existente."""
    monkeypatch.setattr(agent_cli.config, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(agent_cli.config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(agent_cli.config, "COMMANDS_DIR", tmp_path / "commands")
    monkeypatch.setattr(agent_cli.config, "COMMANDS_PENDING", tmp_path / "commands" / "pending")
    monkeypatch.setattr(agent_cli.config, "COMMANDS_RUNNING", tmp_path / "commands" / "running")
    monkeypatch.setattr(agent_cli.config, "COMMANDS_DONE", tmp_path / "commands" / "done")
    monkeypatch.setattr(agent_cli.config, "AGENT_REPO_ROOT", tmp_path / "repos")
    agent_cli.ensure_queue_dirs()
    (tmp_path / "projects" / "meu-app").mkdir(parents=True)
    (tmp_path / "repos").mkdir()
    return tmp_path


def _enqueue(queue: Path, type_: CommandType, project_id="meu-app", args=None) -> QueuedCommand:
    cmd = QueuedCommand(id=str(uuid.uuid4()), type=type_, project_id=project_id, args=args or {})
    (queue / "commands" / "pending" / f"{cmd.id}.json").write_text(cmd.model_dump_json())
    return cmd


def _result(queue: Path, cmd_id: str) -> CommandResult:
    return CommandResult.model_validate_json(
        (queue / "commands" / "done" / f"{cmd_id}.json").read_text()
    )


def _ok_proc():
    p = MagicMock()
    p.returncode = 0
    p.stdout = "ok"
    p.stderr = ""
    return p


# ── claim ────────────────────────────────────────────────────────────

class TestClaim:
    def test_claim_move_para_running(self, queue):
        cmd = _enqueue(queue, CommandType.run)
        claimed = agent_cli.claim_next()
        assert claimed is not None
        assert claimed.parent.name == "running"
        assert not (queue / "commands" / "pending" / f"{cmd.id}.json").exists()

    def test_fila_vazia_retorna_none(self, queue):
        assert agent_cli.claim_next() is None

    def test_claim_pega_o_mais_antigo(self, queue):
        c1 = _enqueue(queue, CommandType.run)
        time.sleep(0.02)
        _enqueue(queue, CommandType.kill, project_id=None)
        claimed = agent_cli.claim_next()
        assert claimed.stem == c1.id


# ── validação ────────────────────────────────────────────────────────

class TestValidate:
    def test_run_em_projeto_existente_ok(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.run, project_id="meu-app")
        assert agent_cli.validate(cmd) is None

    def test_run_em_projeto_inexistente_falha(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.run, project_id="nao-existe")
        assert "não existe" in agent_cli.validate(cmd)

    def test_project_id_com_traversal_falha(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.run, project_id="../etc")
        assert "inválido" in agent_cli.validate(cmd)

    def test_new_project_duplicado_falha(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.new_project, project_id="meu-app")
        assert "já existe" in agent_cli.validate(cmd)

    def test_new_project_backend_invalido(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.new_project,
                            project_id="novo", args={"backend": "aider"})
        assert "backend inválido" in agent_cli.validate(cmd)

    def test_new_project_repo_fora_da_raiz_falha(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.new_project,
                            project_id="novo", args={"repo_path": "/etc/repo"})
        assert "fora de" in agent_cli.validate(cmd)

    def test_plan_mode_invalido(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.plan_tasks,
                            project_id="meu-app", args={"mode": "destroy"})
        assert "mode inválido" in agent_cli.validate(cmd)

    def test_split_task_id_invalido(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.split_task,
                            project_id="meu-app", args={"task_id": "x; rm -rf /"})
        assert "task_id inválido" in agent_cli.validate(cmd)

    def test_kill_nao_precisa_de_projeto(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.kill)
        assert agent_cli.validate(cmd) is None


# ── argv ─────────────────────────────────────────────────────────────

class TestBuildArgv:
    def test_new_project_argv(self, queue):
        cmd = QueuedCommand(
            id="x", type=CommandType.new_project, project_id="novo",
            args={"name": "Novo", "stack": "python,flask", "backend": "litellm",
                  "git_init": True},
        )
        argv = agent_cli.build_argv(cmd)
        assert argv[1:3] == ["new", "novo"]
        assert "--yes" in argv and "--git-init" in argv
        assert argv[argv.index("--backend") + 1] == "litellm"

    def test_plan_tasks_argv(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.plan_tasks, project_id="meu-app",
                            args={"description": "API REST", "mode": "replace"})
        argv = agent_cli.build_argv(cmd)
        assert "plan" in argv and "--yes" in argv
        assert argv[argv.index("--mode") + 1] == "replace"
        assert argv[argv.index("--desc") + 1] == "API REST"

    def test_run_argv(self, queue):
        cmd = QueuedCommand(id="x", type=CommandType.run, project_id="meu-app")
        assert agent_cli.build_argv(cmd)[1:] == ["bg", "meu-app"]


# ── execução ─────────────────────────────────────────────────────────

class TestExecute:
    def test_comando_valido_executa_e_grava_done(self, queue):
        cmd = _enqueue(queue, CommandType.run)
        claimed = agent_cli.claim_next()
        with patch.object(agent_cli.subprocess, "run", return_value=_ok_proc()) as run:
            result = agent_cli.execute(claimed)
        run.assert_called_once()
        assert run.call_args.kwargs.get("env") is not None
        assert result.status == CommandStatus.done
        assert _result(queue, cmd.id).status == CommandStatus.done
        assert not claimed.exists()

    def test_comando_invalido_nao_executa_subprocess(self, queue):
        cmd = _enqueue(queue, CommandType.run, project_id="nao-existe")
        claimed = agent_cli.claim_next()
        with patch.object(agent_cli.subprocess, "run") as run:
            result = agent_cli.execute(claimed)
        run.assert_not_called()
        assert result.status == CommandStatus.failed
        assert "não existe" in _result(queue, cmd.id).error

    def test_exit_code_diferente_de_zero_vira_failed(self, queue):
        cmd = _enqueue(queue, CommandType.run)
        claimed = agent_cli.claim_next()
        proc = _ok_proc()
        proc.returncode = 1
        proc.stderr = "Sessão ativa"
        with patch.object(agent_cli.subprocess, "run", return_value=proc):
            result = agent_cli.execute(claimed)
        assert result.status == CommandStatus.failed
        assert "Sessão ativa" in result.stderr_tail

    def test_json_invalido_vira_failed(self, queue):
        bad = queue / "commands" / "running" / "lixo.json"
        bad.write_text("{nao é json")
        result = agent_cli.execute(bad)
        assert result.status == CommandStatus.failed
        assert not bad.exists()


# ── órfãos + TTL ─────────────────────────────────────────────────────

class TestRecovery:
    def test_orfaos_viram_failed_sem_reexecucao(self, queue):
        cmd = QueuedCommand(id="orfao-1", type=CommandType.run, project_id="meu-app")
        (queue / "commands" / "running" / "orfao-1.json").write_text(cmd.model_dump_json())
        with patch.object(agent_cli.subprocess, "run") as run:
            count = agent_cli.recover_orphans()
        run.assert_not_called()
        assert count == 1
        result = _result(queue, "orfao-1")
        assert result.status == CommandStatus.failed
        assert "reiniciado" in result.error

    def test_cleanup_apaga_resultados_velhos(self, queue, monkeypatch):
        old = queue / "commands" / "done" / "velho.json"
        old.write_text("{}")
        os.utime(old, (time.time() - 90000, time.time() - 90000))  # ~25h atrás
        novo = queue / "commands" / "done" / "novo.json"
        novo.write_text("{}")
        monkeypatch.setattr(agent_cli.config, "COMMAND_RESULT_TTL_HOURS", 24)
        deleted = agent_cli.cleanup_done()
        assert deleted == 1
        assert not old.exists() and novo.exists()


# ── --once drena a fila ──────────────────────────────────────────────

class TestRunOnce:
    def test_once_processa_tudo_e_sai(self, queue):
        _enqueue(queue, CommandType.run)
        _enqueue(queue, CommandType.kill, project_id=None)
        with patch.object(agent_cli.subprocess, "run", return_value=_ok_proc()):
            code = agent_cli.run_agent(once=True)
        assert code == 0
        assert len(list((queue / "commands" / "done").glob("*.json"))) == 2
        assert list((queue / "commands" / "pending").glob("*.json")) == []
