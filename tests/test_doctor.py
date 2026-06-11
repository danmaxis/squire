"""Testes para 'squire doctor' (doctor.py)."""
from __future__ import annotations

import fcntl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import doctor
from models import Alert, AlertList, AlertSeverity, SessionLock


# ── state root ───────────────────────────────────────────────────────

class TestStateRoot:
    def test_ok_quando_existe_e_gravavel(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor.config, "STATE_ROOT", tmp_path)
        monkeypatch.setattr(doctor.config, "PROJECTS_DIR", tmp_path / "projects")
        (tmp_path / "projects").mkdir()
        results = doctor.check_state_root()
        assert all(r.status == doctor.OK for r in results)

    def test_fail_quando_nao_existe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor.config, "STATE_ROOT", tmp_path / "nope")
        results = doctor.check_state_root()
        assert results[0].status == doctor.FAIL

    def test_warn_sem_projects_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor.config, "STATE_ROOT", tmp_path)
        monkeypatch.setattr(doctor.config, "PROJECTS_DIR", tmp_path / "projects")
        results = doctor.check_state_root()
        assert results[0].status == doctor.OK
        assert results[1].status == doctor.WARN


# ── LLM endpoint ─────────────────────────────────────────────────────

def _mock_models_response(ids: list[str]):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": [{"id": i} for i in ids]}
    return resp


class TestLLMEndpoint:
    def test_ok_com_modelo_disponivel(self, monkeypatch):
        monkeypatch.setattr(doctor.config, "LITELLM_MODEL", "m1")
        monkeypatch.setattr(doctor.config, "MODEL_LOW", "m1")
        monkeypatch.setattr(doctor.config, "MODEL_MEDIUM", "m1")
        monkeypatch.setattr(doctor.config, "MODEL_HIGH", "m1")
        with patch.object(doctor.httpx, "get", return_value=_mock_models_response(["m1"])):
            results = doctor.check_llm_endpoint()
        assert all(r.status == doctor.OK for r in results)

    def test_warn_modelo_ausente(self, monkeypatch):
        monkeypatch.setattr(doctor.config, "LITELLM_MODEL", "m1")
        monkeypatch.setattr(doctor.config, "MODEL_LOW", "m1")
        monkeypatch.setattr(doctor.config, "MODEL_MEDIUM", "m1")
        monkeypatch.setattr(doctor.config, "MODEL_HIGH", "m1")
        with patch.object(doctor.httpx, "get", return_value=_mock_models_response(["outro"])):
            results = doctor.check_llm_endpoint()
        assert results[0].status == doctor.OK       # endpoint
        assert results[1].status == doctor.WARN     # modelo

    def test_fail_endpoint_inacessivel(self):
        with patch.object(doctor.httpx, "get", side_effect=ConnectionError("boom")):
            results = doctor.check_llm_endpoint()
        assert results[0].status == doctor.FAIL


# ── claude binary ────────────────────────────────────────────────────

class TestClaudeBin:
    def test_fail_quando_ausente(self):
        with patch.object(doctor.shutil, "which", return_value=None):
            results = doctor.check_claude_bin()
        assert results[0].status == doctor.FAIL

    def test_ok_com_versao(self):
        proc = MagicMock(stdout="9.9.9 (Claude Code)\n", stderr="")
        with (
            patch.object(doctor.shutil, "which", return_value="/usr/bin/claude"),
            patch.object(doctor.subprocess, "run", return_value=proc),
        ):
            results = doctor.check_claude_bin()
        assert results[0].status == doctor.OK
        assert "9.9.9" in results[0].detail


# ── backend binaries ─────────────────────────────────────────────────

class TestBackendBins:
    def test_litellm_nao_checa_binario(self, monkeypatch):
        with patch.object(doctor, "_backends_in_use", return_value={"litellm"}):
            assert doctor.check_backend_bins() == []

    def test_fail_binario_ausente(self):
        with (
            patch.object(doctor, "_backends_in_use", return_value={"opencode"}),
            patch.object(doctor.shutil, "which", return_value=None),
        ):
            results = doctor.check_backend_bins()
        assert results[0].status == doctor.FAIL

    def test_ok_binario_presente(self):
        with (
            patch.object(doctor, "_backends_in_use", return_value={"crush"}),
            patch.object(doctor.shutil, "which", return_value="/usr/bin/crush"),
        ):
            results = doctor.check_backend_bins()
        assert results[0].status == doctor.OK


# ── session.lock ─────────────────────────────────────────────────────

def _write_lock(path: Path, pid: int, age_minutes: int = 0, ttl: int = 60) -> None:
    lock = SessionLock(
        holder="sess-test",
        project_id="proj",
        acquired_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        ttl_minutes=ttl,
        pid=pid,
    )
    path.write_text(lock.model_dump_json())


class TestSessionLock:
    @pytest.fixture(autouse=True)
    def _lock_file(self, tmp_path, monkeypatch):
        self.lock_path = tmp_path / "session.lock"
        monkeypatch.setattr(doctor.config, "SESSION_LOCK_FILE", self.lock_path)

    def test_ok_sem_lock(self):
        results = doctor.check_session_lock()
        assert results[0].status == doctor.OK

    def test_warn_lock_de_pid_vivo(self):
        import os
        _write_lock(self.lock_path, pid=os.getpid())
        results = doctor.check_session_lock()
        assert results[0].status == doctor.WARN
        assert "ativa" in results[0].detail

    def test_warn_lock_stale_sem_fix(self):
        _write_lock(self.lock_path, pid=99999999)
        results = doctor.check_session_lock(fix=False)
        assert results[0].status == doctor.WARN
        assert self.lock_path.exists()

    def test_fix_remove_lock_stale(self):
        _write_lock(self.lock_path, pid=99999999)
        results = doctor.check_session_lock(fix=True)
        assert results[0].status == doctor.OK
        assert not self.lock_path.exists()

    def test_fix_nao_remove_lock_de_pid_vivo(self):
        import os
        _write_lock(self.lock_path, pid=os.getpid())
        doctor.check_session_lock(fix=True)
        assert self.lock_path.exists()


# ── llm.lock ─────────────────────────────────────────────────────────

class TestLLMLock:
    @pytest.fixture(autouse=True)
    def _state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor.config, "STATE_ROOT", tmp_path)
        self.lock_path = tmp_path / "llm.lock"

    def test_ok_sem_arquivo(self):
        results = doctor.check_llm_lock()
        assert results[0].status == doctor.OK

    def test_ok_arquivo_residual_livre(self):
        self.lock_path.write_text("123.45")
        results = doctor.check_llm_lock(fix=False)
        assert results[0].status == doctor.OK
        assert self.lock_path.exists()

    def test_fix_remove_arquivo_livre(self):
        self.lock_path.write_text("123.45")
        results = doctor.check_llm_lock(fix=True)
        assert results[0].status == doctor.OK
        assert not self.lock_path.exists()

    def test_warn_lock_em_uso(self):
        self.lock_path.write_text("")
        held = open(self.lock_path, "w")
        fcntl.flock(held, fcntl.LOCK_EX)
        try:
            results = doctor.check_llm_lock(fix=True)
            assert results[0].status == doctor.WARN
            assert self.lock_path.exists()  # --fix não remove lock em uso
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)
            held.close()


# ── alerts ───────────────────────────────────────────────────────────

class TestAlerts:
    def test_ok_sem_pendentes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor.config, "ALERTS_FILE", tmp_path / "alerts.json")
        results = doctor.check_alerts()
        assert results[0].status == doctor.OK

    def test_warn_com_pendentes(self, tmp_path, monkeypatch):
        path = tmp_path / "alerts.json"
        path.write_text(AlertList(alerts=[
            Alert(project_id="p", severity=AlertSeverity.critical,
                  type="x", message="m"),
        ]).model_dump_json())
        monkeypatch.setattr(doctor.config, "ALERTS_FILE", path)
        results = doctor.check_alerts()
        assert results[0].status == doctor.WARN
        assert "1 pendente(s)" in results[0].detail


# ── run_doctor exit code ─────────────────────────────────────────────

class TestRunDoctor:
    def test_exit_1_com_fail(self, capsys):
        fail = [doctor.CheckResult(doctor.FAIL, "x", "broken")]
        ok = [doctor.CheckResult(doctor.OK, "y")]
        with (
            patch.object(doctor, "check_state_root", return_value=fail),
            patch.object(doctor, "check_llm_endpoint", return_value=ok),
            patch.object(doctor, "check_claude_bin", return_value=ok),
            patch.object(doctor, "check_backend_bins", return_value=[]),
            patch.object(doctor, "check_session_lock", return_value=ok),
            patch.object(doctor, "check_llm_lock", return_value=ok),
            patch.object(doctor, "check_projects", return_value=[]),
            patch.object(doctor, "check_alerts", return_value=ok),
            patch.object(doctor, "check_stats_freshness", return_value=ok),
        ):
            assert doctor.run_doctor() == 1

    def test_exit_0_sem_fail(self, capsys):
        ok = [doctor.CheckResult(doctor.OK, "y")]
        warn = [doctor.CheckResult(doctor.WARN, "z", "meh")]
        with (
            patch.object(doctor, "check_state_root", return_value=ok),
            patch.object(doctor, "check_llm_endpoint", return_value=warn),
            patch.object(doctor, "check_claude_bin", return_value=ok),
            patch.object(doctor, "check_backend_bins", return_value=[]),
            patch.object(doctor, "check_session_lock", return_value=ok),
            patch.object(doctor, "check_llm_lock", return_value=ok),
            patch.object(doctor, "check_projects", return_value=[]),
            patch.object(doctor, "check_alerts", return_value=ok),
            patch.object(doctor, "check_stats_freshness", return_value=ok),
        ):
            assert doctor.run_doctor() == 0
