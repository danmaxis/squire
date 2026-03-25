"""Testes unitários para o Orchestrator — foco no ciclo de rodadas e productive wait."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from models import (
    Checkpoint,
    GlobalStats,
    LLMContextSummary,
    Project,
    ProjectStatus,
    RateLimitState,
    RecoveryHints,
    Task,
    TaskList,
    TaskStatus,
)


# ── Helpers ─────────────────────────────────────────────────────────

def make_task(**kwargs) -> Task:
    defaults = dict(
        id="task-001", title="Test task", description="Do something",
        status=TaskStatus.pending, attempts=0, max_attempts=10,
        homologation_attempt=0, max_homologation_attempts=5,
    )
    defaults.update(kwargs)
    return Task(**defaults)


def make_orchestrator(can_call_side_effect=None):
    """
    Cria um Orchestrator com todas as dependências externas mockadas.
    """
    from orchestrator import Orchestrator

    project = Project(
        id="test-proj", name="Test Project", description="Test",
        repo_path="/tmp/repo", status=ProjectStatus.implementing,
    )
    task_list = TaskList(tasks=[make_task()])
    cp = Checkpoint(session_id="sess-test")
    stats = GlobalStats()

    with (
        patch("orchestrator.ckpt.load_project", return_value=project),
        patch("orchestrator.ckpt.load_tasks", return_value=task_list),
        patch("orchestrator.ckpt.load_checkpoint", return_value=cp),
        patch("orchestrator.ckpt.load_stats", return_value=stats),
        patch("orchestrator.InnerLoop"),
        patch("orchestrator.Homologator"),
        patch("orchestrator.TechnicalEscalation"),
    ):
        orch = Orchestrator("test-proj", dry_run=False, verbose=False)

    # Substituir rate_limiter por mock controlável
    orch.rate_limiter = MagicMock()
    if can_call_side_effect is not None:
        orch.rate_limiter.can_call.side_effect = can_call_side_effect
    else:
        orch.rate_limiter.can_call.return_value = True
    orch.rate_limiter.wait_seconds.return_value = 1500  # 25 min

    # Mock de _save_state para não tocar em disco
    orch._save_state = MagicMock()
    orch._record_event = MagicMock()

    return orch


def make_homolog_result(approved=True, feedback="ok", summary="", fix_suggestion="", error=None):
    r = MagicMock()
    r.approved = approved
    r.summary = summary
    r.feedback = feedback
    r.fix_suggestion = fix_suggestion
    r.error = error
    return r


# ── TestWaitProductively ─────────────────────────────────────────────

class TestWaitProductively:
    def test_nao_chama_inner_loop_quando_pode_chamar(self):
        """Se can_call() é True, não entra no loop produtivo."""
        orch = make_orchestrator(can_call_side_effect=[True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "")

        orch._run_inner_loop.assert_not_called()

    def test_chama_inner_loop_uma_vez_durante_rate_limit(self):
        """Se can_call() retorna False uma vez e depois True, inner loop roda uma vez."""
        orch = make_orchestrator(can_call_side_effect=[False, True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "feedback anterior")

        orch._run_inner_loop.assert_called_once_with(
            task, homologation_feedback="feedback anterior"
        )

    def test_chama_inner_loop_multiplas_vezes_se_rate_limit_persiste(self):
        """Enquanto can_call() retorna False, continua rodando o inner loop."""
        orch = make_orchestrator(can_call_side_effect=[False, False, False, True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "meu feedback")

        assert orch._run_inner_loop.call_count == 3
        for c in orch._run_inner_loop.call_args_list:
            assert c == call(task, homologation_feedback="meu feedback")

    def test_reseta_attempts_antes_de_cada_inner_loop(self):
        """task.attempts deve ser zerado antes de cada rodada do inner loop."""
        orch = make_orchestrator(can_call_side_effect=[False, False, True])
        task = make_task(attempts=7)
        attempts_before_call = []

        def capture_attempts(*args, **kwargs):
            attempts_before_call.append(task.attempts)
            task.attempts = 5
            return True

        orch._run_inner_loop = capture_attempts

        orch._wait_productively(task, "")

        assert attempts_before_call == [0, 0]

    def test_feedback_vazio_funciona(self):
        """Feedback vazio não causa erro."""
        orch = make_orchestrator(can_call_side_effect=[False, True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=False)

        orch._wait_productively(task, "")

        orch._run_inner_loop.assert_called_once_with(task, homologation_feedback="")


# ── TestRunHomologation ──────────────────────────────────────────────

class TestRunHomologation:
    """
    Com o novo design (Ralph Loop), _run_homologation:
    - Roda inner loop NO INÍCIO de cada rodada (não só na rejeição)
    - Sempre homologa, independente do resultado dos testes
    - max_homologation_attempts = número de rodadas completas
    """

    def test_aprovado_na_primeira_rodada(self):
        """Inner loop roda, homologação aprova → True."""
        orch = make_orchestrator()
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("orchestrator.time") as mock_time:
            result = orch._run_homologation(task)

        assert result is True
        assert task.homologation_result == "approved"
        orch._run_inner_loop.assert_called_once()

    def test_inner_loop_chamado_no_inicio_de_cada_rodada(self):
        """Inner loop deve ser chamado uma vez por rodada."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=3)
        orch._run_inner_loop = MagicMock(return_value=False)  # testes sempre falham
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="precisa melhorar"
        )

        with patch("orchestrator.time"):
            orch._run_homologation(task)

        # 3 rodadas → 3 chamadas ao inner loop (uma por rodada)
        assert orch._run_inner_loop.call_count == 3

    def test_homologa_mesmo_com_testes_falhando(self):
        """Inner loop retorna False (testes falham) → homologação ainda ocorre."""
        orch = make_orchestrator()
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=False)  # testes falham
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("orchestrator.time"):
            result = orch._run_homologation(task)

        assert result is True
        orch.homologator.review.assert_called_once()

    def test_rejeitado_todas_rodadas_retorna_false(self):
        """Esgotando todas as rodadas sem aprovação → False."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=2)
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="não satisfaz"
        )

        with patch("orchestrator.time"):
            result = orch._run_homologation(task)

        assert result is False
        assert task.homologation_result == "rejected"
        assert orch.homologator.review.call_count == 2

    def test_feedback_da_rejeicao_usado_na_rodada_seguinte(self):
        """Feedback da rejeição deve chegar como homologation_feedback no inner loop seguinte."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=2)

        inner_loop_feedbacks = []

        def capture_inner(t, homologation_feedback=""):
            inner_loop_feedbacks.append(homologation_feedback)
            return True

        orch._run_inner_loop = capture_inner
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="falta empty state"),
            make_homolog_result(approved=True),
        ]

        with patch("orchestrator.time"):
            orch._run_homologation(task)

        # Rodada 1: sem feedback anterior (ainda vazio)
        assert inner_loop_feedbacks[0] == ""
        # Rodada 2: contexto estruturado contendo o feedback da rejeição
        assert "falta empty state" in inner_loop_feedbacks[1]

    def test_productive_wait_chamado_antes_de_cada_homologacao(self):
        """_wait_productively deve ser chamado antes de cada chamada ao homologador."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=3)
        orch._wait_productively = MagicMock()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="fb1"),
            make_homolog_result(approved=False, feedback="fb2"),
            make_homolog_result(approved=True),
        ]

        with patch("orchestrator.time"):
            orch._run_homologation(task)

        # 3 rodadas → 3 chamadas ao _wait_productively
        assert orch._wait_productively.call_count == 3

    def test_aprovado_na_terceira_rodada(self):
        """Aprovação na terceira rodada → True, tentativas anteriores foram esgotadas."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=5)
        orch._run_inner_loop = MagicMock(return_value=False)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="fb1"),
            make_homolog_result(approved=False, feedback="fb2"),
            make_homolog_result(approved=True),
        ]

        with patch("orchestrator.time"):
            result = orch._run_homologation(task)

        assert result is True
        assert task.homologation_attempt == 3
        assert orch._run_inner_loop.call_count == 3

    def test_attempts_resetado_no_inicio_de_cada_rodada(self):
        """task.attempts deve ser zerado no início de cada rodada."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=2)
        attempts_at_start = []

        def capture(t, homologation_feedback=""):
            attempts_at_start.append(t.attempts)
            t.attempts = 7  # simula progresso dentro do inner loop
            return True

        orch._run_inner_loop = capture
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="x"
        )

        with patch("orchestrator.time"):
            orch._run_homologation(task)

        assert attempts_at_start == [0, 0]

    def test_pausa_de_5s_antes_de_cada_homologacao(self):
        """Deve chamar time.sleep(5) antes de cada homologação."""
        orch = make_orchestrator()
        task = make_task(max_homologation_attempts=2)
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="fb"),
            make_homolog_result(approved=True),
        ]

        with patch("orchestrator.time") as mock_time:
            orch._run_homologation(task)

        assert mock_time.sleep.call_count == 2
        mock_time.sleep.assert_called_with(5)
