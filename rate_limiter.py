"""
Rate limiter — controla a frequência de chamadas ao Claude Code.

Regra: máximo de N chamadas a cada M minutos.
Se exceder, retorna tempo de espera restante.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from models import RateLimitState
import config


class RateLimiter:
    """Controla o rate limit de chamadas ao Claude Code."""

    def __init__(self, state: RateLimitState | None = None):
        self.state = state or RateLimitState(
            max_calls_per_window=config.CLAUDE_CODE_MAX_CALLS_PER_WINDOW,
            window_duration_minutes=config.CLAUDE_CODE_WINDOW_MINUTES,
        )

    def can_call(self) -> bool:
        """Verifica se pode fazer uma chamada agora."""
        self._maybe_reset_window()
        return self.state.claude_code_calls_this_window < self.state.max_calls_per_window

    def record_call(self) -> None:
        """Registra uma chamada feita."""
        self._maybe_reset_window()
        self.state.claude_code_calls_this_window += 1

    def wait_seconds(self) -> int:
        """Retorna quantos segundos faltam até a janela resetar. 0 se pode chamar."""
        if self.can_call():
            return 0
        window_end = self.state.window_started_at + timedelta(
            minutes=self.state.window_duration_minutes
        )
        remaining = (window_end - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def wait_if_needed(self) -> None:
        """Bloqueia até poder fazer a próxima chamada."""
        wait = self.wait_seconds()
        if wait > 0:
            print(f"[rate-limit] Aguardando {wait}s até próxima janela...")
            time.sleep(wait)
            self._maybe_reset_window()

    def _maybe_reset_window(self) -> None:
        """Reseta a janela se o tempo expirou."""
        window_end = self.state.window_started_at + timedelta(
            minutes=self.state.window_duration_minutes
        )
        if datetime.utcnow() >= window_end:
            self.state.claude_code_calls_this_window = 0
            self.state.window_started_at = datetime.utcnow()
