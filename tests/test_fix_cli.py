"""Testes do squire fix (fix_cli.py) — ciclo de correção de task bloqueada."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import checkpoint as ckpt
import fix_cli
from homologator import HomologationResult
from models import (
    GlobalStats, HomologationLog, HomologationLogEntry, Project, Task,
    TaskList, TaskStatus, TokenUsage,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def state(tmp_path, monkeypatch):
    """STATE_ROOT temporário com projeto + task bloqueada + repo git fake."""
    for mod in (ckpt, fix_cli):
        monkeypatch.setattr(mod.config, "STATE_ROOT", tmp_path)
        monkeypatch.setattr(mod.config, "PROJECTS_DIR", tmp_path / "projects")
        monkeypatch.setattr(
            mod.config, "project_dir", lambda pid, _t=tmp_path: _t / "projects" / pid
        )
        monkeypatch.setattr(mod.config, "SESSION_LOCK_FILE", tmp_path / "session.lock")
        monkeypatch.setattr(mod.config, "STATS_FILE", tmp_path / "global-stats.json")

    pdir = tmp_path / "projects" / "proj"
    pdir.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()

    project = Project(
        id="proj", name="Proj", description="", repo_path=str(repo),
        stack=["python"], status="blocked",
    )
    (pdir / "project.json").write_text(project.model_dump_json())

    task = Task(
        id="task-001", title="Tarefa travada", status=TaskStatus.blocked,
        homologation_attempt=5, rejection_summaries=["resumo antigo 1", "resumo antigo 2"],
    )
    (pdir / "tasks.json").write_text(TaskList(tasks=[task]).model_dump_json())
    return tmp_path


USAGE = TokenUsage(prompt_tokens=100, completion_tokens=50, cost_usd=0.05, model="claude-x")
APPROVED = HomologationResult(approved=True, summary="correto agora", usage=USAGE)
REJECTED = HomologationResult(
    approved=False, summary="ainda falta X", feedback="detalhes longos",
    fix_suggestion="faça Y", usage=USAGE,
)
INFRA = HomologationResult(error="Parse error", error_kind="infra", usage=USAGE)


def _mock_innerloop():
    il = MagicMock()
    il.snapshot_test_hashes.return_value = {"tests/test_a.py": "abc"}
    il.check_test_integrity.return_value = []
    il.run_tests.return_value = {"success": True, "passing": 5, "failing": 0, "output": "ok"}
    return il


def _run(state, implement=( ["src/a.py"], USAGE ), review_results=None, il=None):
    review_results = review_results or [APPROVED]
    il = il or _mock_innerloop()
    with (
        patch.object(fix_cli, "InnerLoop", return_value=il),
        patch.object(fix_cli.TechnicalEscalation, "implement_directly",
                     return_value=implement) as impl,
        patch.object(fix_cli.Homologator, "review", side_effect=review_results) as review,
        patch.object(fix_cli.time, "sleep"),
    ):
        code = fix_cli.run_fix("proj", "task-001")
    return code, impl, review, il


def _task(state) -> Task:
    return TaskList.model_validate_json(
        (state / "projects" / "proj" / "tasks.json").read_text()
    ).tasks[0]


# ── Recusas ──────────────────────────────────────────────────────────

class TestRefusals:
    def test_projeto_inexistente(self, state):
        assert fix_cli.run_fix("nao-existe", "task-001") == 1

    def test_task_inexistente(self, state):
        assert fix_cli.run_fix("proj", "task-999") == 1

    def test_task_nao_bloqueada(self, state):
        tasks_path = state / "projects" / "proj" / "tasks.json"
        tl = TaskList.model_validate_json(tasks_path.read_text())
        tl.tasks[0].status = TaskStatus.pending
        tasks_path.write_text(tl.model_dump_json())
        assert fix_cli.run_fix("proj", "task-001") == 2

    def test_lock_ativo_recusa(self, state):
        import os
        ckpt.acquire_lock("sess-outra", "outro-proj")
        # lock de pid vivo (o nosso) não é roubado
        lock_path = state / "session.lock"
        data = json.loads(lock_path.read_text())
        data["pid"] = os.getpid()
        lock_path.write_text(json.dumps(data, default=str))
        code, *_ = _run(state)
        assert code == 3


# ── Caminho aprovado ─────────────────────────────────────────────────

class TestApproved:
    def test_aprovada_completa_e_loga(self, state):
        code, impl, review, il = _run(state)
        assert code == 0
        task = _task(state)
        assert task.status == TaskStatus.completed
        assert task.claude_code_assisted is True
        assert task.homologation_attempt == 6
        log = ckpt.load_homologation_log("proj")
        assert log.entries[-1].source == "fix"
        assert log.entries[-1].approved is True
        # lock liberado
        assert not (state / "session.lock").exists()

    def test_status_do_projeto_recalculado(self, state):
        code, *_ = _run(state)
        assert code == 0
        project = ckpt.load_project("proj")
        assert project.status.value == "completed"  # única task → tudo done

    def test_custos_contabilizados(self, state):
        code, *_ = _run(state)
        stats = ckpt.load_stats()
        assert stats.daily_claude_code_calls == 2  # implement + review
        assert stats.cost_estimate_usd == pytest.approx(0.10)
        assert _task(state).cost_usd == pytest.approx(0.10)

    def test_contexto_usa_fallback_de_rejection_summaries(self, state):
        # sem homologation_log → contexto vem dos summaries + guard de testes
        code, impl, *_ = _run(state)
        rejection_context = impl.call_args.kwargs["rejection_context"]
        assert "resumo antigo 1" in rejection_context
        assert "PROIBIDO modificar arquivos de teste" in rejection_context

    def test_contexto_prefere_homologation_log(self, state):
        ckpt.append_homologation_entry("proj", HomologationLogEntry(
            task_id="task-001", attempt=4, approved=False,
            summary="resumo do log", fix_suggestion="conserte Z",
            feedback="bem detalhado",
        ))
        code, impl, *_ = _run(state)
        rejection_context = impl.call_args.kwargs["rejection_context"]
        assert "conserte Z" in rejection_context
        assert "resumo antigo 1" not in rejection_context


# ── Caminho rejeitado / falhas ───────────────────────────────────────

class TestRejectedAndFailures:
    def test_rejeitada_permanece_blocked_exit_6(self, state):
        code, *_ = _run(state, review_results=[REJECTED])
        assert code == 6
        task = _task(state)
        assert task.status == TaskStatus.blocked
        assert task.rejection_summaries[-1] == "ainda falta X"
        assert task.homologation_attempt == 6
        log = ckpt.load_homologation_log("proj")
        assert log.entries[-1].approved is False
        assert log.entries[-1].fix_suggestion == "faça Y"
        assert not (state / "session.lock").exists()

    def test_implement_sem_arquivos_exit_4(self, state):
        code, *_ = _run(state, implement=([], None))
        assert code == 4
        assert _task(state).status == TaskStatus.blocked

    def test_infra_persistente_exit_5_task_intocada(self, state):
        code, _, review, _ = _run(state, review_results=[INFRA, INFRA])
        assert code == 5
        assert review.call_count == 2  # 1 retry de infra
        task = _task(state)
        assert task.status == TaskStatus.blocked
        assert task.homologation_attempt == 5  # rodada não consumida
        assert ckpt.load_homologation_log("proj").entries == []

    def test_infra_depois_aprovada(self, state):
        code, _, review, _ = _run(state, review_results=[INFRA, APPROVED])
        assert code == 0
        assert review.call_count == 2

    def test_testes_alterados_sao_revertidos(self, state):
        il = _mock_innerloop()
        il.check_test_integrity.return_value = ["tests/test_a.py"]
        code, *_ , il_out = _run(state, il=il)
        il.revert_test_files.assert_called_once_with(["tests/test_a.py"])
        assert code == 0  # fix continua após reverter
