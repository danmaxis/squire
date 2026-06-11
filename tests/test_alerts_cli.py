"""Testes para 'squire alerts' (alerts_cli.py)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import alerts_cli
from models import Alert, AlertList, AlertSeverity


# ── Helpers ──────────────────────────────────────────────────────────

def _alert(project: str, task: str | None, acked: bool = False,
           severity: AlertSeverity = AlertSeverity.critical) -> Alert:
    return Alert(
        project_id=project,
        severity=severity,
        type="max_homologations_reached",
        task_id=task,
        message=f"Task {task} falhou",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        acknowledged=acked,
    )


@pytest.fixture
def alerts_file(tmp_path, monkeypatch):
    """Aponta config.ALERTS_FILE para um arquivo temporário com 4 alertas."""
    path = tmp_path / "alerts.json"
    alerts = AlertList(alerts=[
        _alert("proj-a", "task-001"),                 # idx 1
        _alert("proj-a", "task-002", acked=True),     # reconhecido (sem índice)
        _alert("proj-b", "task-003"),                 # idx 2
        _alert("proj-b", None),                       # idx 3
    ])
    path.write_text(alerts.model_dump_json())
    monkeypatch.setattr(alerts_cli.config, "ALERTS_FILE", path)
    return path


def _load(path: Path) -> AlertList:
    return AlertList.model_validate_json(path.read_text())


# ── Index resolution ─────────────────────────────────────────────────

class TestIndexedUnacked:
    def test_indices_pulam_reconhecidos(self, alerts_file):
        alerts = alerts_cli.ckpt.load_alerts()
        indexed = alerts_cli._indexed_unacked(alerts)
        assert [i for i, _ in indexed] == [1, 2, 3]
        assert indexed[1][1].task_id == "task-003"  # idx 2 = proj-b/task-003

    def test_indice_fora_do_alcance_sai_com_erro(self, alerts_file):
        alerts = alerts_cli.ckpt.load_alerts()
        with pytest.raises(SystemExit):
            alerts_cli._resolve_indexes(alerts, ["9"])

    def test_indice_nao_numerico_sai_com_erro(self, alerts_file):
        alerts = alerts_cli.ckpt.load_alerts()
        with pytest.raises(SystemExit):
            alerts_cli._resolve_indexes(alerts, ["abc"])


# ── ack ──────────────────────────────────────────────────────────────

class TestAck:
    def test_ack_por_indice(self, alerts_file):
        alerts_cli.cmd_ack(["2"])
        result = _load(alerts_file)
        assert result.alerts[2].acknowledged is True   # proj-b/task-003
        assert result.alerts[0].acknowledged is False  # não tocou idx 1

    def test_ack_all(self, alerts_file):
        alerts_cli.cmd_ack([], ack_all=True)
        result = _load(alerts_file)
        assert all(a.acknowledged for a in result.alerts)

    def test_ack_por_projeto(self, alerts_file):
        alerts_cli.cmd_ack([], project="proj-b")
        result = _load(alerts_file)
        assert result.alerts[0].acknowledged is False  # proj-a intocado
        assert result.alerts[2].acknowledged is True
        assert result.alerts[3].acknowledged is True

    def test_ack_por_task(self, alerts_file):
        alerts_cli.cmd_ack([], task="task-001")
        result = _load(alerts_file)
        assert result.alerts[0].acknowledged is True
        assert result.alerts[2].acknowledged is False

    def test_ack_sem_args_sai_com_erro(self, alerts_file):
        with pytest.raises(SystemExit):
            alerts_cli.cmd_ack([])

    def test_ack_preserva_contrato_json(self, alerts_file):
        """O shape gravado precisa continuar compatível com o dashboard."""
        alerts_cli.cmd_ack(["1"])
        raw = json.loads(alerts_file.read_text())
        entry = raw["alerts"][0]
        assert set(entry) >= {
            "project_id", "severity", "type", "task_id",
            "message", "created_at", "acknowledged",
        }
        assert entry["acknowledged"] is True


# ── rm ───────────────────────────────────────────────────────────────

class TestRm:
    def test_rm_por_indice(self, alerts_file):
        alerts_cli.cmd_rm(["1"])
        result = _load(alerts_file)
        assert len(result.alerts) == 3
        assert result.alerts[0].task_id == "task-002"  # o reconhecido ficou

    def test_rm_acked(self, alerts_file):
        alerts_cli.cmd_rm([], rm_acked=True)
        result = _load(alerts_file)
        assert len(result.alerts) == 3
        assert not any(a.acknowledged for a in result.alerts)

    def test_rm_all(self, alerts_file):
        alerts_cli.cmd_rm([], rm_all=True)
        result = _load(alerts_file)
        assert result.alerts == []

    def test_rm_sem_args_sai_com_erro(self, alerts_file):
        with pytest.raises(SystemExit):
            alerts_cli.cmd_rm([])


# ── list ─────────────────────────────────────────────────────────────

class TestList:
    def test_list_mostra_pendentes(self, alerts_file, capsys):
        alerts_cli.cmd_list()
        out = capsys.readouterr().out
        assert "task-001" in out
        assert "task-003" in out
        assert "task-002" not in out  # reconhecido não aparece sem --all

    def test_list_all_inclui_reconhecidos(self, alerts_file, capsys):
        alerts_cli.cmd_list(show_all=True)
        out = capsys.readouterr().out
        assert "task-002" in out

    def test_list_filtra_por_projeto(self, alerts_file, capsys):
        alerts_cli.cmd_list(project="proj-a")
        out = capsys.readouterr().out
        assert "task-001" in out
        assert "task-003" not in out

    def test_list_vazio(self, alerts_file, capsys):
        alerts_cli.cmd_rm([], rm_all=True)
        capsys.readouterr()
        alerts_cli.cmd_list()
        out = capsys.readouterr().out
        assert "Nenhum alerta" in out
