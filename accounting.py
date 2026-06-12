"""
Contabilidade de uso/custo compartilhada entre o orquestrador (squire.py)
e o ciclo de fix (fix_cli.py). Mantém GlobalStats e Task.cost_usd em
sincronia com cada chamada de LLM/Claude realizada.
"""

from __future__ import annotations

from typing import Optional

from models import GlobalStats, Task, TokenUsage


def record_usage(
    stats: GlobalStats,
    usage: Optional[TokenUsage],
    task: Optional[Task] = None,
    cc_call: bool = True,
) -> float:
    """Aplica uma chamada já realizada em GlobalStats (in-place) e na task.

    Retorna o custo registrado. cc_call=True identifica chamadas ao Claude
    Code (contam em daily_calls_unknown_cost quando a usage não veio).
    O caller persiste stats (save_stats) quando fizer sentido.
    """
    if usage is None:
        if cc_call:
            stats.daily_calls_unknown_cost += 1
        return 0.0

    cost = max(0.0, float(usage.cost_usd or 0.0))
    tokens = int(usage.prompt_tokens or 0) + int(usage.completion_tokens or 0)
    stats.cost_estimate_usd += cost
    stats.daily_tokens += tokens
    if usage.tokens_unknown and cc_call:
        stats.daily_calls_unknown_cost += 1
    if usage.model:
        stats.cost_by_model[usage.model] = (
            stats.cost_by_model.get(usage.model, 0.0) + cost
        )
    if task is not None:
        task.cost_usd = float(task.cost_usd or 0.0) + cost
    return cost
