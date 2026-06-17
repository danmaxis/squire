"""Testes do retry gratuito de infra na homologação (_review_with_infra_retry)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from homologator import HomologationResult
from models import GlobalStats, LLMContextSummary, Task
from squire import Squire


def _bare_squire():
    s = Squire.__new__(Squire)
    s.stats = GlobalStats(date="2026-06-11")
    s.session_cost_usd = 0.0
    s.session_cc_calls = 0
    s.homologator = MagicMock()
    s.rate_limiter = MagicMock()
    s.rate_limiter.can_afford.return_value = True
    s.cp = MagicMock()
    s.cp.llm_context = LLMContextSummary()
    return s


def _task() -> Task:
    return Task(id="task-001", title="T", homologation_attempt=1)


INFRA_ERROR = HomologationResult(error="Parse error: x", error_kind="infra")
CONFIG_ERROR = HomologationResult(error="binário ausente", error_kind="config")
APPROVED = HomologationResult(approved=True, summary="ok")


class TestInfraRetry:
    def test_erro_infra_ganha_um_retry(self):
        s = _bare_squire()
        s.homologator.review.side_effect = [INFRA_ERROR, APPROVED]
        with patch("squire.time.sleep"):
            result = s._review_with_infra_retry(_task(), None)
        assert result.approved is True
        assert s.homologator.review.call_count == 2

    def test_dois_erros_infra_devolvem_o_erro(self):
        s = _bare_squire()
        s.homologator.review.side_effect = [INFRA_ERROR, INFRA_ERROR]
        with patch("squire.time.sleep"):
            result = s._review_with_infra_retry(_task(), None)
        assert result.error_kind == "infra"
        assert s.homologator.review.call_count == 2  # nunca mais que 1 retry

    def test_erro_config_nao_ganha_retry(self):
        s = _bare_squire()
        s.homologator.review.side_effect = [CONFIG_ERROR, APPROVED]
        result = s._review_with_infra_retry(_task(), None)
        assert result.error_kind == "config"
        assert s.homologator.review.call_count == 1

    def test_rejeicao_real_nao_ganha_retry(self):
        s = _bare_squire()
        rejected = HomologationResult(approved=False, feedback="faltou X")
        s.homologator.review.side_effect = [rejected]
        result = s._review_with_infra_retry(_task(), None)
        assert result.approved is False
        assert s.homologator.review.call_count == 1

    def test_sem_budget_nao_ha_retry(self):
        s = _bare_squire()
        s.rate_limiter.can_afford.return_value = False
        s.homologator.review.side_effect = [INFRA_ERROR]
        result = s._review_with_infra_retry(_task(), None)
        assert result.error_kind == "infra"
        assert s.homologator.review.call_count == 1

    def test_cada_chamada_e_contabilizada(self):
        s = _bare_squire()
        s.homologator.review.side_effect = [INFRA_ERROR, APPROVED]
        with patch("squire.time.sleep"):
            s._review_with_infra_retry(_task(), None)
        assert s.rate_limiter.record_call.call_count == 2
        assert s.stats.daily_claude_code_calls == 2
