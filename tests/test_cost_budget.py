"""
Testes para cost tracking + USD budget rate limit (Feature #2 + Improv #B).

Cobre:
- Cálculo de custo a partir de tokens via tabela de preços (config)
- LiteLLMBackend popula `usage` a partir do campo `usage` da resposta OpenAI
- OpenCode/Crush sinalizam `tokens_unknown=True`
- Homologator extrai `total_cost_usd` + tokens do JSON do Claude Code
- _unwrap_claude_json é defensivo com stdout não-JSON
- RateLimiter.can_afford gate combina call-count + budget USD
- RateLimiter.refund desconta corretamente
- _maybe_reset_daily_budget zera contador ao virar o dia
- budget_used_pct + budget_remaining_usd refletem o estado
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import config
from models import RateLimitState, TokenUsage
from rate_limiter import RateLimiter


# ── Pricing helpers ────────────────────────────────────────────────────

class TestPriceTable:
    def test_modelo_conhecido_retorna_par(self):
        assert config.price_for_model("claude-opus-4-7") == (15.0, 75.0)
        assert config.price_for_model("claude-sonnet-4-6") == (3.0, 15.0)
        assert config.price_for_model("journal-synth") == (0.0, 0.0)

    def test_prefix_match_para_variantes(self):
        # Modelo com sufixo (ex: "[1m]") deve casar pelo prefix
        assert config.price_for_model("claude-opus-4-7[1m]") == (15.0, 75.0)

    def test_modelo_desconhecido_retorna_zero(self):
        assert config.price_for_model("gpt-9000") == (0.0, 0.0)
        assert config.price_for_model("") == (0.0, 0.0)

    def test_compute_cost_calcula_corretamente(self):
        # 1M input + 1M output em claude-opus-4-7 = $15 + $75 = $90
        cost = config.compute_cost_usd(1_000_000, 1_000_000, "claude-opus-4-7")
        assert cost == pytest.approx(90.0)

    def test_compute_cost_pequeno_volume(self):
        # 1000 input + 500 output em sonnet-4-6 = (1000*3 + 500*15)/1e6
        cost = config.compute_cost_usd(1000, 500, "claude-sonnet-4-6")
        assert cost == pytest.approx(0.0105)

    def test_compute_cost_modelo_local_zero(self):
        cost = config.compute_cost_usd(100_000, 50_000, "journal-synth")
        assert cost == 0.0


# ── LiteLLM backend usage extraction ──────────────────────────────────

class TestLiteLLMUsage:
    def _backend(self):
        from backends import LiteLLMBackend
        return LiteLLMBackend(model="claude-sonnet-4-6", base_url="http://x", api_key="k")

    def test_extract_usage_com_tokens_calcula_custo(self):
        b = self._backend()
        data = {"usage": {"prompt_tokens": 2000, "completion_tokens": 1000}}
        u = b._extract_usage(data)
        assert u.prompt_tokens == 2000
        assert u.completion_tokens == 1000
        assert u.model == "claude-sonnet-4-6"
        assert u.tokens_unknown is False
        # 2000*3 + 1000*15 = 21000 → 21000/1e6 = $0.021
        assert u.cost_usd == pytest.approx(0.021)

    def test_extract_usage_ausente_marca_unknown(self):
        b = self._backend()
        u = b._extract_usage({})
        assert u.tokens_unknown is True
        assert u.cost_usd == 0.0
        assert u.model == "claude-sonnet-4-6"

    def test_extract_usage_zero_tokens_marca_unknown(self):
        """Alguns gateways locais retornam usage={} ou com zeros — tratar como unknown."""
        b = self._backend()
        u = b._extract_usage({"usage": {"prompt_tokens": 0, "completion_tokens": 0}})
        assert u.tokens_unknown is True


# ── OpenCode/Crush backends sinalizam unknown ─────────────────────────

class TestCliBackendsUnknown:
    def test_opencode_sempre_unknown(self, tmp_path):
        from backends import OpenCodeBackend
        b = OpenCodeBackend(opencode_bin="opencode")
        proc = MagicMock(returncode=0, stdout="done", stderr="")
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm); cm.__exit__ = MagicMock(return_value=False)
        with patch("backends.subprocess.run", return_value=proc), \
             patch("backends._LLMLock", return_value=cm), \
             patch.object(b, "_git_diff_files", return_value=[]):
            r = b.execute_instruction("x", tmp_path, 30, task_hint={"title": "foo"})
        assert r.usage is not None
        assert r.usage.tokens_unknown is True

    def test_crush_sempre_unknown(self, tmp_path):
        from backends import CrushBackend
        b = CrushBackend(crush_bin="crush")
        proc = MagicMock(returncode=0, stdout="done", stderr="")
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm); cm.__exit__ = MagicMock(return_value=False)
        with patch("backends.subprocess.run", return_value=proc), \
             patch("backends._LLMLock", return_value=cm), \
             patch.object(b, "_git_diff_files", return_value=[]):
            r = b.execute_instruction("x", tmp_path, 30)
        assert r.usage is not None
        assert r.usage.tokens_unknown is True


# ── Homologator usage extraction ──────────────────────────────────────

class TestHomologatorUsage:
    def test_extract_usage_da_resposta_completa(self):
        from homologator import _extract_usage_from_claude_json
        data = {
            "total_cost_usd": 0.42,
            "model": "claude-opus-4-7",
            "usage": {
                "input_tokens": 5000,
                "output_tokens": 1500,
                "cache_read_input_tokens": 2000,
            },
            "result": "ok",
        }
        u = _extract_usage_from_claude_json(data)
        assert u is not None
        assert u.prompt_tokens == 5000
        assert u.completion_tokens == 1500
        assert u.cached_tokens == 2000
        assert u.cost_usd == 0.42
        assert u.model == "claude-opus-4-7"
        assert u.tokens_unknown is False

    def test_extract_usage_sem_cost_fallback_calcula_da_tabela(self):
        """Se Claude omitir total_cost_usd mas reportar tokens + model, calcula via tabela."""
        from homologator import _extract_usage_from_claude_json
        data = {
            "model": "claude-sonnet-4-6",
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        }
        u = _extract_usage_from_claude_json(data)
        assert u is not None
        # 1000*3 + 500*15 = 10500 → $0.0105
        assert u.cost_usd == pytest.approx(0.0105)

    def test_extract_usage_sem_campos_relevantes_retorna_none(self):
        from homologator import _extract_usage_from_claude_json
        assert _extract_usage_from_claude_json({"result": "ok"}) is None
        assert _extract_usage_from_claude_json(None) is None

    def test_unwrap_claude_json_com_stdout_valido(self):
        from homologator import _unwrap_claude_json
        stdout = (
            '{"result": "instruções aqui", "total_cost_usd": 0.05, '
            '"model": "claude-sonnet-4-6", "usage": {"input_tokens": 100, "output_tokens": 50}}'
        )
        text, usage = _unwrap_claude_json(stdout)
        assert text == "instruções aqui"
        assert usage is not None
        assert usage.cost_usd == 0.05

    def test_unwrap_claude_json_com_stdout_nao_json_retorna_tupla_compat(self):
        """Stdout sem JSON → retorna (raw, None) sem quebrar."""
        from homologator import _unwrap_claude_json
        text, usage = _unwrap_claude_json("plain text response")
        assert text == "plain text response"
        assert usage is None


# ── RateLimiter budget gate ──────────────────────────────────────────

def _state(**kwargs) -> RateLimitState:
    defaults = dict(
        claude_code_calls_this_window=0,
        window_started_at=datetime.now(timezone.utc),
        window_duration_minutes=30,
        max_calls_per_window=10,
        max_daily_usd=0.0,
        daily_cost_usd=0.0,
        daily_cost_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    defaults.update(kwargs)
    return RateLimitState(**defaults)


class TestCanAfford:
    def test_sem_budget_permite_qualquer_custo(self):
        rl = RateLimiter(_state(max_daily_usd=0.0, daily_cost_usd=100.0))
        # Sem cap → custo arbitrário deve ser permitido (apenas call-count limita)
        assert rl.can_afford(50.0) is True

    def test_com_budget_e_folga_permite(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=2.0))
        assert rl.can_afford(1.0) is True   # 2+1 ≤ 10
        assert rl.can_afford(8.0) is True   # 2+8 = 10 ≤ 10 (boundary)

    def test_com_budget_estouraria_bloqueia(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=9.5))
        assert rl.can_afford(1.0) is False  # 9.5+1.0 > 10

    def test_call_count_secundario_ainda_bloqueia_sem_budget(self):
        """Mesmo sem budget, call-count exhausted bloqueia."""
        rl = RateLimiter(_state(max_daily_usd=0.0, claude_code_calls_this_window=10, max_calls_per_window=10))
        assert rl.can_afford(0.0) is False

    def test_can_call_backward_compat(self):
        """can_call() é atalho para can_afford(0): bloqueia quando budget já estourou."""
        # No boundary (10+0 ≤ 10): permitido
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=10.0))
        assert rl.can_call() is True
        # Acima do cap: bloqueado
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=11.0))
        assert rl.can_call() is False


class TestRecordCallCost:
    def test_record_call_acumula_custo(self):
        rl = RateLimiter(_state(max_daily_usd=10.0))
        rl.record_call(cost_usd=0.5)
        rl.record_call(cost_usd=1.5)
        assert rl.state.daily_cost_usd == pytest.approx(2.0)
        assert rl.state.claude_code_calls_this_window == 2

    def test_record_call_cost_zero_so_incrementa_counter(self):
        rl = RateLimiter(_state())
        rl.record_call()  # default cost=0
        assert rl.state.daily_cost_usd == 0.0
        assert rl.state.claude_code_calls_this_window == 1

    def test_record_call_custo_negativo_eh_clampado_a_zero(self):
        rl = RateLimiter(_state())
        rl.record_call(cost_usd=-5.0)
        assert rl.state.daily_cost_usd == 0.0


class TestRefund:
    def test_refund_subtrai_custo(self):
        rl = RateLimiter(_state(daily_cost_usd=5.0))
        rl.refund(2.0)
        assert rl.state.daily_cost_usd == pytest.approx(3.0)

    def test_refund_nao_vai_abaixo_de_zero(self):
        rl = RateLimiter(_state(daily_cost_usd=1.0))
        rl.refund(5.0)
        assert rl.state.daily_cost_usd == 0.0

    def test_refund_de_valor_nao_positivo_eh_noop(self):
        rl = RateLimiter(_state(daily_cost_usd=3.0))
        rl.refund(0.0)
        rl.refund(-1.0)
        assert rl.state.daily_cost_usd == 3.0


class TestDailyBudgetReset:
    def test_reseta_quando_dia_vira(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=8.0, daily_cost_date="2020-01-01"))
        # _maybe_reset_daily_budget é chamado implicitamente em can_afford
        assert rl.can_afford(5.0) is True  # após reset, 0+5 ≤ 10
        assert rl.state.daily_cost_usd == 0.0
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert rl.state.daily_cost_date == today

    def test_nao_reseta_no_mesmo_dia(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rl = RateLimiter(_state(daily_cost_usd=8.0, daily_cost_date=today))
        rl._maybe_reset_daily_budget()
        assert rl.state.daily_cost_usd == 8.0


class TestBudgetIntrospection:
    def test_budget_used_pct(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=2.5))
        assert rl.budget_used_pct() == pytest.approx(0.25)

    def test_budget_used_pct_sem_cap_retorna_zero(self):
        rl = RateLimiter(_state(max_daily_usd=0.0, daily_cost_usd=5.0))
        assert rl.budget_used_pct() == 0.0

    def test_budget_remaining_usd(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=3.0))
        assert rl.budget_remaining_usd() == pytest.approx(7.0)

    def test_budget_remaining_clamp_no_excesso(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=15.0))
        assert rl.budget_remaining_usd() == 0.0

    def test_budget_remaining_sem_cap_eh_infinito(self):
        rl = RateLimiter(_state(max_daily_usd=0.0))
        import math
        assert math.isinf(rl.budget_remaining_usd())


class TestBudgetWarnings:
    def test_warn_75pct_uma_vez(self, capsys):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=7.0))
        rl.record_call(cost_usd=1.0)  # 7+1 = 8 → 80% → cruza 75%
        rl.record_call(cost_usd=0.1)  # já avisou
        out = capsys.readouterr().out
        assert out.count("75%") == 1

    def test_warn_100pct_uma_vez(self, capsys):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=5.0))
        rl.record_call(cost_usd=6.0)  # 5+6=11 → 110%
        rl.record_call(cost_usd=0.5)
        out = capsys.readouterr().out
        assert "esgotado" in out.lower()
        assert out.lower().count("esgotado") == 1


class TestWaitSeconds:
    def test_zero_quando_pode_chamar(self):
        rl = RateLimiter(_state())
        assert rl.wait_seconds() == 0

    def test_budget_exhausted_aguarda_ate_midnight(self):
        rl = RateLimiter(_state(max_daily_usd=10.0, daily_cost_usd=10.5))
        # > 0 e ≤ 86400s (1 dia)
        secs = rl.wait_seconds()
        assert secs > 0
        assert secs <= 86400
