"""Testes das flags não-interativas de tasks_cli (rm/split/plan/add --yes etc.).

A regra central: com as flags certas, NENHUM input() pode disparar — os
testes monkeypatcham builtins.input para levantar AssertionError.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import tasks_cli
from models import Project, Task, TaskList


# ── Helpers ──────────────────────────────────────────────────────────

def _setup_project(tmp_path, monkeypatch, project_id: str = "proj", tasks: list[Task] | None = None):
    """Monta um projeto mínimo num STATE_ROOT temporário."""
    projects_dir = tmp_path / "projects"
    pdir = projects_dir / project_id
    pdir.mkdir(parents=True)

    repo = tmp_path / "repo"
    repo.mkdir()

    project = Project(
        id=project_id, name="Proj", description="", repo_path=str(repo),
        stack=["python"], status="planning",
    )
    (pdir / "project.json").write_text(project.model_dump_json())
    (pdir / "tasks.json").write_text(
        TaskList(tasks=tasks or []).model_dump_json()
    )

    monkeypatch.setattr(tasks_cli.config, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(tasks_cli.config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(
        tasks_cli.config, "project_dir", lambda pid: projects_dir / pid
    )
    return pdir


def _forbid_input(monkeypatch):
    monkeypatch.setattr(
        "builtins.input",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("prompt disparou")),
    )


def _load_tasks(pdir: Path) -> TaskList:
    return TaskList.model_validate_json((pdir / "tasks.json").read_text())


PLAN_RESPONSE = json.dumps({
    "tasks": [
        {"id": "task-100", "title": "Nova A", "description": "d", "effort": "low",
         "tdd": False, "test_author": "claude", "max_attempts": 10,
         "max_homologation_attempts": 5, "skip_homologation": False},
        {"id": "task-101", "title": "Nova B", "description": "d", "effort": "medium",
         "tdd": True, "test_author": "local", "max_attempts": 10,
         "max_homologation_attempts": 5, "skip_homologation": False},
    ]
})

SPLIT_RESPONSE = json.dumps({
    "subtasks": [
        {"title": "Sub 1", "description": "a", "effort": "low", "tdd": False},
        {"title": "Sub 2", "description": "b", "effort": "low", "tdd": False},
    ]
})


# ── rm --yes ─────────────────────────────────────────────────────────

class TestRmYes:
    def test_rm_yes_remove_sem_prompt(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch, tasks=[Task(id="task-001", title="T")])
        _forbid_input(monkeypatch)
        tasks_cli.cmd_rm("proj", "task-001", assume_yes=True)
        assert _load_tasks(pdir).tasks == []

    def test_rm_sem_yes_continua_pedindo_confirmacao(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch, tasks=[Task(id="task-001", title="T")])
        monkeypatch.setattr("builtins.input", lambda *a: "n")
        with pytest.raises(SystemExit):
            tasks_cli.cmd_rm("proj", "task-001")
        assert len(_load_tasks(pdir).tasks) == 1


# ── split --yes ──────────────────────────────────────────────────────

class TestSplitYes:
    def test_split_yes_aceita_primeira_proposta(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch, tasks=[Task(id="task-001", title="Grande")])
        _forbid_input(monkeypatch)
        with patch.object(tasks_cli, "_call_claude", return_value=SPLIT_RESPONSE) as call:
            tasks_cli.cmd_split("proj", "task-001", assume_yes=True)
        assert call.call_count == 1  # sem refinamento
        task = _load_tasks(pdir).tasks[0]
        assert len(task.subtasks) == 2
        assert task.subtasks[0].id == "task-001-sub01"


# ── plan --yes / --mode / --no-refine ────────────────────────────────

class TestPlanNonInteractive:
    def test_plan_yes_append_sem_prompt(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch, tasks=[Task(id="task-001", title="Velha")])
        _forbid_input(monkeypatch)
        with patch.object(tasks_cli, "_call_claude", return_value=PLAN_RESPONSE) as call:
            tasks_cli.cmd_plan("proj", desc="API REST", assume_yes=True)
        assert call.call_count == 1  # uma chamada, sem refinamento
        tasks = _load_tasks(pdir).tasks
        assert [t.id for t in tasks] == ["task-001", "task-100", "task-101"]  # append

    def test_plan_mode_replace(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch, tasks=[Task(id="task-001", title="Velha")])
        _forbid_input(monkeypatch)
        with patch.object(tasks_cli, "_call_claude", return_value=PLAN_RESPONSE):
            tasks_cli.cmd_plan("proj", desc="x", mode="replace", assume_yes=True)
        tasks = _load_tasks(pdir).tasks
        assert [t.id for t in tasks] == ["task-100", "task-101"]

    def test_plan_yes_sem_desc_usa_nome_do_projeto(self, tmp_path, monkeypatch):
        _setup_project(tmp_path, monkeypatch)
        _forbid_input(monkeypatch)
        with patch.object(tasks_cli, "_call_claude", return_value=PLAN_RESPONSE):
            tasks_cli.cmd_plan("proj", assume_yes=True)  # não pode prompter

    def test_plan_interativo_enter_default_append(self, tmp_path, monkeypatch):
        """Enter no prompt [r/a] agora significa adicionar (era erro)."""
        pdir = _setup_project(tmp_path, monkeypatch, tasks=[Task(id="task-001", title="Velha")])
        monkeypatch.setattr("builtins.input", lambda *a: "")  # Enter em tudo
        with patch.object(tasks_cli, "_call_claude", return_value=PLAN_RESPONSE):
            tasks_cli.cmd_plan("proj", desc="x")
        tasks = _load_tasks(pdir).tasks
        assert len(tasks) == 3  # apendou em vez de cancelar

    def test_plan_no_refine_pula_loop(self, tmp_path, monkeypatch):
        _setup_project(tmp_path, monkeypatch)
        # input só deve ser chamado para o SPEC prompt — que não existe (sem SPEC.md)
        _forbid_input(monkeypatch)
        with patch.object(tasks_cli, "_call_claude", return_value=PLAN_RESPONSE) as call:
            tasks_cli.cmd_plan("proj", desc="x", refine=False, spec=False)
        assert call.call_count == 1


# ── add --spec/--no-spec ─────────────────────────────────────────────

class TestAddSpecFlag:
    def test_add_no_spec_nao_pergunta(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch)
        repo = Path(json.loads((pdir / "project.json").read_text())["repo_path"])
        (repo / "docs").mkdir()
        (repo / "docs" / "SPEC.md").write_text("# spec")  # SPEC existe → prompt dispararia
        _forbid_input(monkeypatch)
        tasks_cli.cmd_add("proj", "Título", ask_advanced=False, spec=False)
        assert len(_load_tasks(pdir).tasks) == 1

    def test_add_spec_true_roda_spec_update(self, tmp_path, monkeypatch):
        pdir = _setup_project(tmp_path, monkeypatch)
        repo = Path(json.loads((pdir / "project.json").read_text())["repo_path"])
        (repo / "docs").mkdir()
        (repo / "docs" / "SPEC.md").write_text("# spec")
        _forbid_input(monkeypatch)
        with patch.object(tasks_cli, "cmd_spec_update") as spec_update:
            tasks_cli.cmd_add("proj", "Título", ask_advanced=False, spec=True)
        spec_update.assert_called_once_with("proj")
