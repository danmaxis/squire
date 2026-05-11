"""
Rate limiter — controla a frequência e o custo de chamadas ao Claude Code.

Duas linhas de defesa:
1. Window-based call count (existing): N chamadas a cada M minutos —
   pega loops infinitos rapidamente, antes do custo crescer.
2. Daily USD budget (new): teto agregado de custo por dia —
   evita que um único loop caro estoure a fatura mesmo sem violar o call rate.

`can_call()` é mantido como atalho para `can_afford(0.0)` (backward compat).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from models import RateLimitState
import config


class RateLimiter:
    """Controla rate-limit (calls/window) e budget (USD/dia) das chamadas Claude."""

    def __init__(self, state: RateLimitState | None = None):
        self.state = state or RateLimitState(
            max_calls_per_window=config.CLAUDE_CODE_MAX_CALLS_PER_WINDOW,
            window_duration_minutes=config.CLAUDE_CODE_WINDOW_MINUTES,
        )
        # Backfill do budget diário a partir da config quando o state veio
        # de um checkpoint antigo (max_daily_usd=0 por default).
        if not self.state.max_daily_usd and config.DAILY_USD_BUDGET > 0:
            self.state.max_daily_usd = config.DAILY_USD_BUDGET

        # Flags transientes para avisar uma única vez ao cruzar limiares
        self._warned_75 = False
        self._warned_100 = False

    # ── Checks ────────────────────────────────────────────────────────

    def can_call(self) -> bool:
        """Backward-compat: pode chamar agora sem custo estimado?"""
        return self.can_afford(0.0)

    def can_afford(self, estimated_cost_usd: float = 0.0) -> bool:
        """Verifica window calls AND daily budget. True se ambos têm folga."""
        self._maybe_reset_window()
        self._maybe_reset_daily_budget()

        # 1. Call-count (secundário): pega loops infinitos antes do budget estourar
        if self.state.claude_code_calls_this_window >= self.state.max_calls_per_window:
            return False

        # 2. Budget USD diário (primário): só aplica se max_daily_usd > 0
        if self.state.max_daily_usd > 0:
            projected = self.state.daily_cost_usd + estimated_cost_usd
            if projected > self.state.max_daily_usd:
                return False

        return True

    # ── Mutations ─────────────────────────────────────────────────────

    def record_call(self, cost_usd: float = 0.0) -> None:
        """Contabiliza uma chamada e seu custo (em USD)."""
        self._maybe_reset_window()
        self._maybe_reset_daily_budget()
        self.state.claude_code_calls_this_window += 1
        self.state.daily_cost_usd += max(0.0, cost_usd)
        self._maybe_warn_budget_threshold()

    def refund(self, cost_usd: float) -> None:
        """Estorna custo (call falhou antes de produzir output útil)."""
        if cost_usd <= 0:
            return
        self.state.daily_cost_usd = max(0.0, self.state.daily_cost_usd - cost_usd)

    # ── Introspection ─────────────────────────────────────────────────

    def budget_used_pct(self) -> float:
        """Fração do budget diário usada (0–1). Retorna 0 se não há budget setado."""
        if self.state.max_daily_usd <= 0:
            return 0.0
        return self.state.daily_cost_usd / self.state.max_daily_usd

    def budget_remaining_usd(self) -> float:
        """USD restantes hoje. Retorna float('inf') se não há budget setado."""
        if self.state.max_daily_usd <= 0:
            return float("inf")
        return max(0.0, self.state.max_daily_usd - self.state.daily_cost_usd)

    def wait_seconds(self) -> int:
        """Tempo até a próxima janela OU midnight UTC (o que vier primeiro)."""
        if self.can_afford(0.0):
            return 0

        secs_window = 0
        secs_budget = 0

        if self.state.claude_code_calls_this_window >= self.state.max_calls_per_window:
            window_end = self._as_utc(self.state.window_started_at) + timedelta(
                minutes=self.state.window_duration_minutes
            )
            secs_window = max(0, int((window_end - datetime.now(timezone.utc)).total_seconds()))

        if self.state.max_daily_usd > 0 and self.state.daily_cost_usd >= self.state.max_daily_usd:
            now = datetime.now(timezone.utc)
            midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            secs_budget = int((midnight - now).total_seconds())

        # Se ambos limitam, o menor desbloqueio possível ainda exige esperar o maior
        return max(secs_window, secs_budget)

    def wait_if_needed(self) -> None:
        """Bloqueia até poder fazer a próxima chamada."""
        wait = self.wait_seconds()
        if wait > 0:
            print(f"[rate-limit] Aguardando {wait}s até próxima janela/dia...")
            time.sleep(wait)
            self._maybe_reset_window()
            self._maybe_reset_daily_budget()

    # ── Internals ─────────────────────────────────────────────────────

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        """Garante que um datetime é tz-aware (datetimes naive do JSON viram UTC)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _maybe_reset_window(self) -> None:
        """Reseta a janela de calls se o tempo expirou."""
        window_end = self._as_utc(self.state.window_started_at) + timedelta(
            minutes=self.state.window_duration_minutes
        )
        if datetime.now(timezone.utc) >= window_end:
            self.state.claude_code_calls_this_window = 0
            self.state.window_started_at = datetime.now(timezone.utc)

    def _maybe_reset_daily_budget(self) -> None:
        """Zera o gasto diário quando o dia UTC vira."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.state.daily_cost_date != today:
            self.state.daily_cost_usd = 0.0
            self.state.daily_cost_date = today
            self._warned_75 = False
            self._warned_100 = False

    def _maybe_warn_budget_threshold(self) -> None:
        """Loga aviso ao cruzar 75% e ao estourar 100% (uma vez por dia cada)."""
        if self.state.max_daily_usd <= 0:
            return
        pct = self.budget_used_pct()
        used = self.state.daily_cost_usd
        cap = self.state.max_daily_usd
        if pct >= 1.0 and not self._warned_100:
            self._warned_100 = True
            print(f"[budget] ✗ Budget diário esgotado (${used:.2f}/${cap:.2f}) — pausando até midnight UTC")
        elif pct >= 0.75 and not self._warned_75:
            self._warned_75 = True
            print(f"[budget] ⚠ 75% do budget diário usado (${used:.2f}/${cap:.2f})")
