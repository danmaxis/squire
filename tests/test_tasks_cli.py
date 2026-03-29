"""Testes unitários para tasks_cli.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from models import Project, ProjectStatus, Task, TaskList, TaskStatus


# ── Helpers ──────────────────────────────────────────────────────────

def make_project(**kwargs) -> Project:
    defaults = dict(
        id="test-proj", name="Test Project", description="Desc",
        repo_path="/tmp/repo", stack=["python"], status=ProjectStatus.implementing,
    )
    defaults.update(kwargs)
    return Project(**defaults)


def make_task(task_id="task-001", title="Tarefa 1", status=TaskStatus.pending, **kwargs) -> Task:
    return Task(id=task_id, title=title, status=status, **kwargs)


def make_task_list(*tasks: Task) -> TaskList:
    return TaskList(tasks=list(tasks))


# ── Fixtures de patch ────────────────────────────────────────────────

def _patch_project(project=None):
    return patch("tasks_cli.ckpt.load_project", return_value=project or make_project())


def _patch_tasks(task_list=None):
    return patch("tasks_cli.ckpt.load_tasks", return_value=task_list or TaskList())


def _patch_save():
    return patch("tasks_cli.ckpt.save_tasks")


# ── cmd_list ─────────────────────────────────────────────────────────

class TestCmdList:
    def test_lista_vazia(self, capsys):
        from tasks_cli import cmd_list
        with _patch_project(), _patch_tasks(TaskList()):
            cmd_list("test-proj")
        out = capsys.readouterr().out
        assert "nenhuma task" in out

    def test_lista_com_tasks(self, capsys):
        from tasks_cli import cmd_list
        tl = make_task_list(
            make_task("task-001", "Primeira", TaskStatus.completed),
            make_task("task-002", "Segunda", TaskStatus.pending),
            make_task("task-003", "Terceira", TaskStatus.blocked),
        )
        with _patch_project(), _patch_tasks(tl):
            cmd_list("test-proj")
        out = capsys.readouterr().out
        assert "task-001" in out
        assert "Primeira" in out
        assert "task-002" in out
        assert "task-003" in out
        assert "Total: 3" in out

    def test_exibe_skip_homolog(self, capsys):
        from tasks_cli import cmd_list
        tl = make_task_list(make_task("task-001", skip_homologation=True))
        with _patch_project(), _patch_tasks(tl):
            cmd_list("test-proj")
        out = capsys.readouterr().out
        assert "skip-homolog" in out

    def test_projeto_inexistente(self):
        from tasks_cli import cmd_list
        with patch("tasks_cli.ckpt.load_project", return_value=None):
            with pytest.raises(SystemExit) as exc:
                cmd_list("nao-existe")
            assert exc.value.code == 1


# ── cmd_add ──────────────────────────────────────────────────────────

class TestCmdAdd:
    def test_add_auto_id(self):
        from tasks_cli import cmd_add
        saved = []
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", return_value="n"):
            cmd_add("test-proj", title="Nova task")
        assert len(saved) == 1
        assert saved[0].tasks[0].id == "task-001"
        assert saved[0].tasks[0].title == "Nova task"

    def test_add_com_id_explicito(self):
        from tasks_cli import cmd_add
        saved = []
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", return_value="n"):
            cmd_add("test-proj", title="Task X", task_id="task-xyz")
        assert saved[0].tasks[0].id == "task-xyz"

    def test_add_id_duplicado_falha(self):
        from tasks_cli import cmd_add
        tl = make_task_list(make_task("task-001"))
        with _patch_project(), _patch_tasks(tl), patch("builtins.input", return_value="n"):
            with pytest.raises(SystemExit) as exc:
                cmd_add("test-proj", title="Dup", task_id="task-001")
            assert exc.value.code == 1

    def test_add_skip_homologation(self):
        from tasks_cli import cmd_add
        saved = []
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", return_value="n"):
            cmd_add("test-proj", title="Setup", skip_homologation=True)
        assert saved[0].tasks[0].skip_homologation is True

    def test_add_max_attempts(self):
        from tasks_cli import cmd_add
        saved = []
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", return_value="n"):
            cmd_add("test-proj", title="Task", max_attempts=3, max_homologation_attempts=2)
        t = saved[0].tasks[0]
        assert t.max_attempts == 3
        assert t.max_homologation_attempts == 2

    def test_add_auto_id_sequencial(self):
        from tasks_cli import cmd_add
        tl = make_task_list(make_task("task-001"), make_task("task-002"))
        saved = []
        with _patch_project(), _patch_tasks(tl), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", return_value="n"):
            cmd_add("test-proj", title="Terceira")
        assert saved[0].tasks[-1].id == "task-003"

    def test_add_com_advanced_fields(self):
        """Campos avançados (effort/tdd/test_author) salvos quando usuario confirma."""
        from tasks_cli import cmd_add
        from models import Effort, TestAuthor
        saved = []
        # Simula: usuario responde "y" para avançados, depois medium/y/claude
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", side_effect=["y", "medium", "y", "claude"]):
            cmd_add("test-proj", title="TDD Task")
        t = saved[0].tasks[0]
        assert t.effort == Effort.medium
        assert t.tdd is True
        assert t.test_author == TestAuthor.claude


# ── cmd_rm ───────────────────────────────────────────────────────────

class TestCmdRm:
    def test_rm_nao_encontrado(self):
        from tasks_cli import cmd_rm
        tl = make_task_list(make_task("task-001"))
        with _patch_project(), _patch_tasks(tl):
            with pytest.raises(SystemExit) as exc:
                cmd_rm("test-proj", "task-999")
            assert exc.value.code == 1

    def test_rm_confirmado(self):
        from tasks_cli import cmd_rm
        tl = make_task_list(make_task("task-001"), make_task("task-002"))
        saved = []
        with _patch_project(), _patch_tasks(tl), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("builtins.input", return_value="y"):
            cmd_rm("test-proj", "task-001")
        assert len(saved[0].tasks) == 1
        assert saved[0].tasks[0].id == "task-002"

    def test_rm_cancelado(self):
        from tasks_cli import cmd_rm
        tl = make_task_list(make_task("task-001"))
        with _patch_project(), _patch_tasks(tl), \
             patch("tasks_cli.ckpt.save_tasks") as mock_save, \
             patch("builtins.input", return_value="n"):
            with pytest.raises(SystemExit) as exc:
                cmd_rm("test-proj", "task-001")
            mock_save.assert_not_called()
            assert exc.value.code == 0


# ── cmd_split ────────────────────────────────────────────────────────

class TestCmdSplit:
    def _make_claude_response(self, subtasks: list[dict]) -> str:
        """Cria resposta simulada do Claude no formato envelope JSON."""
        inner = json.dumps({"subtasks": subtasks})
        return json.dumps({"result": inner})

    def test_split_salva_subtasks(self):
        from tasks_cli import cmd_split
        tl = make_task_list(make_task("task-001", "Task complexa"))
        subtasks_proposta = [
            {"title": "Sub A", "description": "Desc A"},
            {"title": "Sub B", "description": "Desc B"},
        ]
        saved = []
        with _patch_project(), _patch_tasks(tl), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", return_value=json.dumps({"subtasks": subtasks_proposta})), \
             patch("builtins.input", return_value="y"):
            cmd_split("test-proj", "task-001")

        assert len(saved) == 1
        task_salva = saved[0].tasks[0]
        assert len(task_salva.subtasks) == 2
        assert task_salva.subtasks[0].title == "Sub A"
        assert task_salva.subtasks[1].title == "Sub B"

    def test_split_task_inexistente(self):
        from tasks_cli import cmd_split
        tl = make_task_list(make_task("task-001"))
        with _patch_project(), _patch_tasks(tl):
            with pytest.raises(SystemExit) as exc:
                cmd_split("test-proj", "task-999")
            assert exc.value.code == 1

    def test_split_cancelado(self):
        from tasks_cli import cmd_split
        tl = make_task_list(make_task("task-001"))
        subtasks_proposta = [{"title": "Sub A", "description": ""}]
        with _patch_project(), _patch_tasks(tl), \
             patch("tasks_cli.ckpt.save_tasks") as mock_save, \
             patch("tasks_cli._call_claude", return_value=json.dumps({"subtasks": subtasks_proposta})), \
             patch("builtins.input", return_value="n"):
            with pytest.raises(SystemExit) as exc:
                cmd_split("test-proj", "task-001")
            mock_save.assert_not_called()
            assert exc.value.code == 0

    def test_split_ids_gerados(self):
        from tasks_cli import cmd_split
        tl = make_task_list(make_task("task-002"))
        subtasks_proposta = [
            {"title": "Sub 1", "description": ""},
            {"title": "Sub 2", "description": ""},
            {"title": "Sub 3", "description": ""},
        ]
        saved = []
        with _patch_project(), _patch_tasks(tl), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", return_value=json.dumps({"subtasks": subtasks_proposta})), \
             patch("builtins.input", return_value="y"):
            cmd_split("test-proj", "task-002")

        subtasks = saved[0].tasks[0].subtasks
        assert subtasks[0].id == "task-002-sub01"
        assert subtasks[1].id == "task-002-sub02"
        assert subtasks[2].id == "task-002-sub03"


# ── cmd_plan ─────────────────────────────────────────────────────────

class TestCmdPlan:
    def _claude_plan_response(self, tasks: list[dict]) -> str:
        return json.dumps({"tasks": tasks})

    def test_plan_replace(self):
        from tasks_cli import cmd_plan
        existing = make_task_list(make_task("task-001", "Antiga"))
        novas = [{"id": "task-001", "title": "Nova", "description": "Desc", "max_attempts": 10,
                  "max_homologation_attempts": 5, "skip_homologation": False}]
        saved = []
        with _patch_project(), _patch_tasks(existing), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", return_value=self._claude_plan_response(novas)), \
             patch("builtins.input", side_effect=["ok", "r", "n"]):  # "n" = não gerar SPEC.md
            cmd_plan("test-proj", desc="Descrição do projeto")

        assert len(saved) == 1
        assert len(saved[0].tasks) == 1
        assert saved[0].tasks[0].title == "Nova"

    def test_plan_append(self):
        from tasks_cli import cmd_plan
        existing = make_task_list(make_task("task-001", "Antiga"))
        novas = [{"id": "task-002", "title": "Adicional", "description": "", "max_attempts": 10,
                  "max_homologation_attempts": 5, "skip_homologation": False}]
        saved = []
        with _patch_project(), _patch_tasks(existing), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", return_value=self._claude_plan_response(novas)), \
             patch("builtins.input", side_effect=["ok", "a", "n"]):
            cmd_plan("test-proj", desc="Descrição")

        assert len(saved) == 1
        assert len(saved[0].tasks) == 2
        assert saved[0].tasks[0].title == "Antiga"
        assert saved[0].tasks[1].title == "Adicional"

    def test_plan_sem_tasks_existentes_nao_pergunta_modo(self):
        from tasks_cli import cmd_plan
        novas = [{"id": "task-001", "title": "Primeira", "description": "", "max_attempts": 10,
                  "max_homologation_attempts": 5, "skip_homologation": False}]
        saved = []
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", return_value=self._claude_plan_response(novas)), \
             patch("builtins.input", side_effect=["ok", "n"]):  # "n" = sem SPEC.md
            cmd_plan("test-proj", desc="Desc")

        assert len(saved[0].tasks) == 1

    def test_plan_refinamento(self):
        from tasks_cli import cmd_plan
        """Feedback → Claude é chamado 2x (draft + refinamento)."""
        call_count = []
        novas = [{"id": "task-001", "title": "Refinada", "description": "", "max_attempts": 10,
                  "max_homologation_attempts": 5, "skip_homologation": False}]

        def mock_claude(prompt, **kwargs):
            call_count.append(1)
            return json.dumps({"tasks": novas})

        saved = []
        with _patch_project(), _patch_tasks(TaskList()), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", side_effect=mock_claude), \
             patch("builtins.input", side_effect=["adicione mais detalhes", "ok", "n"]):
            cmd_plan("test-proj", desc="Desc")

        assert len(call_count) == 2  # draft + 1 refinamento

    def test_plan_append_id_collision_gera_novo_id(self):
        from tasks_cli import cmd_plan
        """Se nova task tem mesmo ID que existente no modo append, gera ID novo."""
        existing = make_task_list(make_task("task-001"))
        novas = [{"id": "task-001", "title": "Colisão", "description": "", "max_attempts": 10,
                  "max_homologation_attempts": 5, "skip_homologation": False}]
        saved = []
        with _patch_project(), _patch_tasks(existing), \
             patch("tasks_cli.ckpt.save_tasks", side_effect=lambda pid, tl: saved.append(tl)), \
             patch("tasks_cli._call_claude", return_value=self._claude_plan_response(novas)), \
             patch("builtins.input", side_effect=["ok", "a", "n"]):
            cmd_plan("test-proj", desc="Desc")

        tasks = saved[0].tasks
        assert len(tasks) == 2
        # A task adicionada não pode ter o mesmo ID que a existente
        ids = [t.id for t in tasks]
        assert len(ids) == len(set(ids)), "IDs duplicados após append"
