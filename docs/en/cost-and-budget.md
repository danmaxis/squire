# Cost and Budget

[🇧🇷 Português](../custos-e-orcamento.md) · 🇬🇧 English

Squire tracks the USD cost of every call (Claude and LiteLLM when the
backend reports usage) and enforces two caps: a **global daily USD
budget** and a **per-task USD cap**. This page explains how tracking
works, how to configure caps, and what happens when one exhausts.

## Table of contents

- [What is tracked](#what-is-tracked)
- [Price table](#price-table)
- [Daily USD budget](#daily-usd-budget)
- [Per-task cap](#per-task-cap)
- [Exhaustion behavior](#exhaustion-behavior)
- [Refund on error](#refund-on-error)
- [Tokens unknown](#tokens-unknown)
- [CLI commands](#cli-commands)
- [Insights and remarks](#insights-and-remarks)

## What is tracked

For each call (Claude Code or local backend), squire records:

- **`prompt_tokens`** and **`completion_tokens`** — when the backend exposes them
- **`cached_tokens`** — when applicable (Claude prompt caching)
- **`cost_usd`** — computed via the price table OR read directly from
  Claude's envelope (`total_cost_usd`)
- **`model`** — model string used
- **`tokens_unknown`** — `true` flag when the backend didn't report usage
  (e.g., opencode/crush CLI)

These fields live in the `TokenUsage` struct
([`models.py:270`](../../models.py)).

Accounting is centralized in `Squire._account_call`
([`squire.py:102`](../../squire.py)) which:

1. Adds `cost_usd` to `GlobalStats.cost_estimate_usd` (daily accumulated)
2. Adds `tokens` to `GlobalStats.daily_tokens`
3. Accumulates in `GlobalStats.cost_by_model[model]`
4. Accumulates in `Task.cost_usd` (this task's specific cost)
5. Increments `GlobalStats.daily_calls_unknown_cost` when `tokens_unknown`

And `RateLimiter.record_call(cost_usd=…)`
([`rate_limiter.py`](../../rate_limiter.py)) updates
`state.daily_cost_usd` in the checkpoint so the budget gate works.

## Price table

In `MODEL_PRICING_PER_1M` ([`config.py:73`](../../config.py)):

| Model                | Input ($/1M)  | Output ($/1M) |
| -------------------- | ------------- | ------------- |
| `claude-opus-4-7`    | 15.00         | 75.00         |
| `claude-opus-4-6`    | 15.00         | 75.00         |
| `claude-sonnet-4-6`  | 3.00          | 15.00         |
| `claude-sonnet-4-5`  | 3.00          | 15.00         |
| `claude-haiku-4-5`   | 1.00          | 5.00          |
| `journal-synth`      | 0.00          | 0.00          |

`config.compute_cost_usd(prompt_tokens, completion_tokens, model)` does the
math. Unknown models return `(0, 0)` — squire still records tokens but
treats as free.

For Claude Code (invoked via `claude --print --output-format json`),
the response envelope includes `total_cost_usd` directly — that value
takes precedence over the table calculation, so even if the table goes
stale, the number remains correct.

> **Insight — calculation fallback.**
> If Claude omits `total_cost_usd` but reports tokens + model,
> `_extract_usage_from_claude_json`
> ([`homologator.py:23`](../../homologator.py)) recomposes cost via the
> table. Defense in depth.

## Daily USD budget

Global daily (UTC) USD spending cap. When exceeded, squire pauses until
midnight UTC.

### Configure

Three routes, in precedence order:

1. **Env var:** `SQUIRE_DAILY_USD_BUDGET=10`
2. **CLI:** `squire budget set --daily 10`
3. **Default:** `0` (no limit)

Option 2 persists in `$SQUIRE_STATE_ROOT/budget.json`. Option 1 wins
over 2 if both are set.

```bash
$ squire budget set --daily 10 --per-task 2
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json
  daily_usd:    $10.00
  per_task_usd: $2.00
```

### How the gate works

Before each Claude call, squire calls
`rate_limiter.can_afford(estimated_cost)`
([`rate_limiter.py:can_afford`](../../rate_limiter.py)). The default
estimated_cost is `SQUIRE_ESTIMATED_CALL_USD` (`$0.05`). If the projected
call would exceed budget, returns `False` and squire pauses.

The gate is dual:

```python
def can_afford(self, estimated_cost_usd: float = 0.0) -> bool:
    # 1. Call-count (secondary): catches infinite loops
    if self.claude_code_calls_this_window >= max_calls_per_window:
        return False
    # 2. Daily USD budget (primary): only applies if max_daily_usd > 0
    if self.max_daily_usd > 0:
        if (daily_cost_usd + estimated_cost_usd) > max_daily_usd:
            return False
    return True
```

> **Insight — why call-count AND USD budget?**
> *Defense in depth.* USD cap doesn't catch the case of hundreds of cheap
> calls in a loop (a bug that iterates without producing useful work).
> Call-count doesn't catch the case of one expensive call blowing the
> budget alone. Both together cover both.

### Threshold warnings

When spend crosses 75% of the cap,
`RateLimiter._maybe_warn_budget_threshold`
([`rate_limiter.py`](../../rate_limiter.py)) prints:

```
[budget] ⚠ 75% do budget diário usado ($7.50/$10.00)
```

At 100%:

```
[budget] ✗ Budget diário esgotado ($10.05/$10.00) — pausando até midnight UTC
```

Each warning fires once per day (transient flag). Reset happens
automatically when UTC day rolls.

## Per-task cap

`Task.max_usd` defines an individual USD cap. If `null` or `0`, uses
`PER_TASK_USD_CAP` (global env var, default `0` = no limit).

```json
{
  "id": "task-007",
  "title": "Complex refactor of auth middleware",
  "max_usd": 1.50
}
```

Check happens inside the inner loop
([`squire.py`](../../squire.py) `_run_inner_loop`):

```python
if self._task_budget_exceeded(task):
    cap = task.max_usd or config.PER_TASK_USD_CAP
    log(f"Task budget esgotado (${task.cost_usd:.2f} >= ${cap:.2f}) — pausando", "warn")
    ckpt.add_alert(..., severity=AlertSeverity.warning)
    return False
```

The same check runs at the top of each homologation round, so even if
the cap is exceeded between rounds, the task aborts before spending more.

## Exhaustion behavior

### Daily budget exhausted

Squire **pauses** (does not fail). Behavior depends on context:

- **Before a Claude call:** `can_afford(0.05)` returns `False`, squire
  logs warning, halts the current task. In `_run_homologation`, calls
  `_wait_productively` which keeps the inner loop running with
  accumulated feedback while waiting.
- **Between tasks:** next pending task is tried the next time budget
  has headroom.
- **Auto reset:** when the clock passes midnight UTC, the counter zeros
  in `_maybe_reset_daily_budget`.

### Per-task cap exceeded

The task is marked `blocked`, an Alert (severity warning) is generated
in `alerts.json`, and squire moves to the next pending task. To unblock:

```bash
# Raise the cap and unblock:
$ squire tasks edit my-app task-007  # edit max_usd in JSON
$ squire unblock my-app task-007     # blocked → pending
```

## Refund on error

`RateLimiter.refund(cost_usd)` subtracts an already-recorded cost.
Useful when a Claude call returns an error before producing useful output —
you shouldn't pay for a network failure.

Current state: squire does **not** automatically call refund in all
paths (only the method exists, ready to be used by call sites when a
call error is distinguishable from a model failure). Next iteration will
close that gap. See roadmap in
[/home/ai-debian/.claude/plans/](../../../.claude/plans/).

```python
# Example use (already compatible):
rl.record_call(cost_usd=0.50)   # call attempt
# ... call fails by timeout without producing output ...
rl.refund(0.50)                  # refund
```

## Tokens unknown

OpenCode and Crush (CLIs) don't expose token counts on stdout reliably.
Squire detects this and marks `tokens_unknown=True` in `TokenUsage`.
Effects:

- `cost_usd = 0` is recorded (no way to calculate without tokens)
- `GlobalStats.daily_calls_unknown_cost` is incremented
- The final `squire run` summary shows:

```
⚠ 3 chamada(s) sem usage reportado — custo real pode ser maior
```

> **Remark — don't confuse unknown with free.**
> The local backend (LiteLLM/Qwen) costs $0 *for real* — you paid for
> the hardware once. OpenCode/Crush may be calling paid APIs underneath
> (Anthropic, OpenAI, etc.) — they just don't report via stdout. If
> you run opencode with `OPENAI_API_KEY` set, you're paying per call,
> but squire will show `$0.000` + a `⚠ tokens_unknown`. Use the
> provider's dashboard to confirm.

## CLI commands

### `squire budget` — show state

```bash
$ squire budget
=== Budget — 2026-05-11 (UTC) ===

  Spent hoje:   $7.823  (148,219 tokens)
  Daily cap:    $10.00  (78% usado) ⚠
  Restante:     $2.177
  Per-task cap: $2.00

  Por modelo:
    claude-opus-4-7: $7.823
    journal-synth: $0.000

  ⚠ 3 chamada(s) sem usage reportado — custo real pode ser maior
```

### `squire budget set --daily X --per-task Y`

Persists to `budget.json`. See [CLI section](cli.md#squire-budget-set---daily-x---per-task-y).

### `squire budget reset`

Zeros daily counters (`global-stats.json`). Doesn't touch `budget.json`.

```bash
$ squire budget reset
✓ Contadores diários resetados para 2026-05-11
```

## Full session — example

```bash
# 1. Configure caps
$ squire budget set --daily 5 --per-task 1
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json

# 2. Run (with `max_usd: 1` in tasks.json for one of the tasks)
$ squire run my-app
[14:22:01] → Sessão iniciada: sess-20260511-1422-a3f4c1
...
[14:25:31] ✓ Task concluída: [task-003] Add timeline ($0.342)
...
[14:31:18] ⚠ 75% do budget diário usado ($3.75/$5.00)
...
[14:34:55] ⚠ Task budget esgotado ($1.02 >= $1.00) — pausando task
[14:34:55] ✗ Task bloqueada: task-007

# 3. Inspect
$ squire budget
  Spent hoje:   $4.123  (78,221 tokens)
  Daily cap:    $5.00   (82% usado) ⚠
  Restante:     $0.877
  Per-task cap: $1.00
```

## Insights and remarks

> **Insight — daily budget, not per-session.**
> The budget is daily (UTC) so crashes and restarts don't accidentally
> give you "infinite budget". For a per-session cap, use `Task.max_usd`
> on the first task and let it exhaust.

> **Insight — `tokens_unknown` is honesty, not punishment.**
> Other tools show `$0.00` when they don't know cost. Squire shows
> the known spend **and** explicitly signals "the actual may be higher".
> Fewer surprises on the provider's invoice.

> **Remark — caps don't kill in-flight calls.**
> If a Claude review already started (~5min typical latency), the cap
> doesn't kill the in-flight call. Pause only on **next** call decision.
> To stop immediately: `squire kill` (brutal) or Ctrl+C (graceful).

## Further reading

- [Configuration](configuration.md) — all budget env vars
- [CLI: `squire budget`](cli.md#budget) — subcommand reference
- [Tasks](tasks.md#per-task-cost) — `max_usd` in the Task model context
- [Rate limiting](homologation.md#rate-limiting) — call count + cost defense in depth
