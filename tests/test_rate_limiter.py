"""Testes unitários para o RateLimiter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import RateLimitState
from rate_limiter import RateLimiter


def make_limiter(calls: int = 0, max_calls: int = 10, window_min: int = 30,
                 started_at: datetime | None = None, naive: bool = False) -> RateLimiter:
    """Factory helper para criar um RateLimiter em estado controlado."""
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    if naive:
        # Simula datetime carregado do JSON sem tzinfo (bug original)
        started_at = started_at.replace(tzinfo=None)
    state = RateLimitState(
        claude_code_calls_this_window=calls,
        window_started_at=started_at,
        window_duration_minutes=window_min,
        max_calls_per_window=max_calls,
    )
    return RateLimiter(state)


class TestCanCall:
    def test_pode_chamar_com_janela_vazia(self):
        rl = make_limiter(calls=0, max_calls=10)
        assert rl.can_call() is True

    def test_nao_pode_chamar_quando_limite_atingido(self):
        rl = make_limiter(calls=10, max_calls=10)
        assert rl.can_call() is False

    def test_pode_chamar_com_uma_chamada_restante(self):
        rl = make_limiter(calls=9, max_calls=10)
        assert rl.can_call() is True

    def test_reseta_janela_expirada(self):
        # Janela começou há 31 minutos — deve resetar
        started = datetime.now(timezone.utc) - timedelta(minutes=31)
        rl = make_limiter(calls=10, max_calls=10, window_min=30, started_at=started)
        assert rl.can_call() is True
        assert rl.state.claude_code_calls_this_window == 0

    def test_nao_reseta_janela_ainda_ativa(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=10)
        rl = make_limiter(calls=10, max_calls=10, window_min=30, started_at=started)
        assert rl.can_call() is False
        assert rl.state.claude_code_calls_this_window == 10


class TestNaiveDatetime:
    """Testa compatibilidade com datetimes naive vindos do checkpoint JSON."""

    def test_can_call_com_naive_datetime(self):
        """Não deve lançar TypeError ao comparar naive com aware."""
        rl = make_limiter(calls=5, max_calls=10, naive=True)
        assert rl.can_call() is True  # não deve levantar exceção

    def test_wait_seconds_com_naive_datetime(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=5)
        rl = make_limiter(calls=10, max_calls=10, window_min=30,
                          started_at=started, naive=True)
        secs = rl.wait_seconds()
        assert secs > 0  # ~25 min restantes

    def test_reseta_janela_expirada_com_naive(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=35)
        rl = make_limiter(calls=10, max_calls=10, window_min=30,
                          started_at=started, naive=True)
        assert rl.can_call() is True
        assert rl.state.claude_code_calls_this_window == 0


class TestRecordCall:
    def test_incrementa_contador(self):
        rl = make_limiter(calls=3, max_calls=10)
        rl.record_call()
        assert rl.state.claude_code_calls_this_window == 4

    def test_reseta_antes_de_incrementar_se_janela_expirada(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=35)
        rl = make_limiter(calls=9, max_calls=10, window_min=30, started_at=started)
        rl.record_call()
        assert rl.state.claude_code_calls_this_window == 1  # resetou e incrementou


class TestWaitSeconds:
    def test_zero_quando_pode_chamar(self):
        rl = make_limiter(calls=0, max_calls=10)
        assert rl.wait_seconds() == 0

    def test_retorna_segundos_restantes(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=5)
        rl = make_limiter(calls=10, max_calls=10, window_min=30, started_at=started)
        wait = rl.wait_seconds()
        # ~25 minutos restantes = ~1500s (tolerância de 5s para execução do teste)
        assert 1490 <= wait <= 1505

    def test_zero_quando_janela_expirada(self):
        started = datetime.now(timezone.utc) - timedelta(minutes=35)
        rl = make_limiter(calls=10, max_calls=10, window_min=30, started_at=started)
        assert rl.wait_seconds() == 0
