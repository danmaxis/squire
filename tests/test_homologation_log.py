"""Testes do homologation_log.json (vereditos completos por projeto)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import checkpoint as ckpt
from homologator import HomologationResult
from models import HomologationLog, HomologationLogEntry, LLMContextSummary, GlobalStats, Task
from squire import Squire


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(ckpt.config, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(ckpt.config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(
        ckpt.config, "project_dir", lambda pid: tmp_path / "projects" / pid
    )
    (tmp_path / "projects" / "proj").mkdir(parents=True)
    return tmp_path


def _entry(task_id: str = "task-001", **kw) -> HomologationLogEntry:
    return HomologationLogEntry(task_id=task_id, **kw)


class TestHelpers:
    def test_load_vazio_retorna_modelo_vazio(self, state):
        assert ckpt.load_homologation_log("proj").entries == []

    def test_append_e_roundtrip(self, state):
        ckpt.append_homologation_entry("proj", _entry(
            attempt=2, approved=False,
            summary="resumo", feedback="feedback completo " * 50,
            fix_suggestion="passos concretos", cost_usd=0.04, model="claude-x",
        ))
        log = ckpt.load_homologation_log("proj")
        assert len(log.entries) == 1
        e = log.entries[0]
        assert e.attempt == 2
        assert "feedback completo" in e.feedback
        assert len(e.feedback) > 300  # NÃO truncado
        assert e.model == "claude-x"

    def test_cap_de_50_por_task(self, state):
        for i in range(55):
            ckpt.append_homologation_entry("proj", _entry(attempt=i))
        log = ckpt.load_homologation_log("proj")
        assert len(log.entries) == 50
        # As mais antigas caem; as mais recentes ficam
        assert log.entries[0].attempt == 5
        assert log.entries[-1].attempt == 54

    def test_cap_nao_afeta_outras_tasks(self, state):
        ckpt.append_homologation_entry("proj", _entry(task_id="task-OUTRA"))
        for i in range(52):
            ckpt.append_homologation_entry("proj", _entry(task_id="task-001", attempt=i))
        log = ckpt.load_homologation_log("proj")
        others = [e for e in log.entries if e.task_id == "task-OUTRA"]
        assert len(others) == 1
        assert len([e for e in log.entries if e.task_id == "task-001"]) == 50


class TestLogVerdict:
    def _squire(self, state) -> Squire:
        s = Squire.__new__(Squire)
        s.project_id = "proj"
        s.stats = GlobalStats(date="2026-06-11")
        return s

    def test_veredito_rejeitado_persiste_completo(self, state):
        s = self._squire(state)
        task = Task(id="task-009", title="T", homologation_attempt=3)
        result = HomologationResult(
            approved=False, summary="resumo curto",
            feedback="explicação longa " * 40,
            fix_suggestion="mude X para Y",
            usage=MagicMock(cost_usd=0.05, model="claude-x"),
        )
        s._log_verdict(task, result)
        log = ckpt.load_homologation_log("proj")
        assert log.entries[0].approved is False
        assert log.entries[0].fix_suggestion == "mude X para Y"
        assert log.entries[0].cost_usd == 0.05
        assert log.entries[0].source == "session"

    def test_source_fix(self, state):
        s = self._squire(state)
        task = Task(id="task-001", title="T")
        s._log_verdict(task, HomologationResult(approved=True, summary="ok"), source="fix")
        assert ckpt.load_homologation_log("proj").entries[0].source == "fix"

    def test_falha_de_gravacao_nao_quebra_o_loop(self, state):
        s = self._squire(state)
        task = Task(id="task-001", title="T")
        with patch.object(ckpt, "append_homologation_entry", side_effect=OSError("disk")):
            s._log_verdict(task, HomologationResult(approved=True))  # não levanta
