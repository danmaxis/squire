# Configuration

[🇧🇷 Português](../configuracao.md) · 🇬🇧 English

Every environment variable, config file, and knob in Squire. All values
have sensible defaults; you only need to set what you want to change.

## Table of contents

- [Precedence](#precedence)
- [Environment variables](#environment-variables)
- [Configuration files](#configuration-files)
- [Paths and directories](#paths-and-directories)
- [Price table](#price-table)

## Precedence

Precedence order (strongest to weakest):

1. **Command-line argument** (e.g., `squire run --quiet`)
2. **Environment variable** (e.g., `SQUIRE_DAILY_USD_BUDGET=15`)
3. **Config file** (e.g., `budget.json`)
4. **Hardcoded default** (in `config.py`)

> **Insight — why env vars > files?**
> 12-factor principle: env vars are portable across dev/staging/prod
> without editing files in the repo. The file is a convenient fallback
> for values that rarely change (budget caps) or are personal (paths).

## Environment variables

All start with `SQUIRE_`. Source: [`config.py`](../../config.py).

### Paths

| Variable             | Default                          | Effect                                         |
| -------------------- | -------------------------------- | ---------------------------------------------- |
| `SQUIRE_STATE_ROOT`  | `/home/ai-debian/squire-state`   | Root of persistent state (all JSONs)           |

> [!IMPORTANT]
> No variable is required: `SQUIRE_STATE_ROOT` defaults to
> `/home/ai-debian/squire-state` (same default the `squire` bash wrapper
> uses). Set the env var to point state elsewhere — the test suite does
> this (in `tests/conftest.py`) so it never touches real state.

### Local LLM (OpenAI-compatible endpoint)

Any OpenAI-compatible endpoint works: LiteLLM gateway, **Ollama** (`/v1`),
llama.cpp server. In the current setup, it's Ollama on Zordon
(`http://192.168.50.24:11434/v1`) serving `journal-synth:latest`.

| Variable                | Default                              | Effect                                          |
| ----------------------- | ------------------------------------ | ----------------------------------------------- |
| `SQUIRE_LITELLM_URL`    | `http://localhost:4000/v1`           | OpenAI-compatible endpoint base URL             |
| `SQUIRE_LITELLM_MODEL`  | `journal-synth`                      | Default model (id/alias on the endpoint)        |
| `SQUIRE_LITELLM_KEY`    | `sk-local`                           | API key (placeholder — local endpoints don't enforce) |
| `SQUIRE_MODEL_LOW`      | same as `LITELLM_MODEL`              | Model for `effort=low` tasks                    |
| `SQUIRE_MODEL_MEDIUM`   | same as `LITELLM_MODEL`              | Model for `effort=medium` tasks                 |
| `SQUIRE_MODEL_HIGH`     | same as `LITELLM_MODEL`              | Model for `effort=high` tasks                   |

### Inner loop

| Variable                    | Default | Effect                                                      |
| --------------------------- | ------- | ----------------------------------------------------------- |
| `SQUIRE_INNER_MAX_ATTEMPTS` | `10`    | Attempts per round (per-task override in `tasks.json`)      |
| `SQUIRE_INNER_TIMEOUT`      | `1200`  | Timeout (s) for one backend call                            |

### Backends

| Variable                  | Default     | Effect                                                                  |
| ------------------------- | ----------- | ----------------------------------------------------------------------- |
| `SQUIRE_CODING_BACKEND`   | `opencode`  | Default backend (override in `project.json` via `coding_backend`)        |
| `SQUIRE_OPENCODE_BIN`     | `opencode`  | Opencode binary path/name (searches `$PATH` if relative)                 |
| `SQUIRE_CRUSH_BIN`        | `crush`     | Crush binary path/name                                                   |
| `SQUIRE_AIDER_BIN`        | `aider`     | **Deprecated.** Aider was discontinued; this var has no effect anymore. |

### Claude Code

| Variable                  | Default   | Effect                                                  |
| ------------------------- | --------- | ------------------------------------------------------- |
| `SQUIRE_CLAUDE_BIN`       | `claude`  | Claude Code CLI binary                                  |
| `SQUIRE_CC_MAX_CALLS`     | `10`      | Max calls per window (secondary rate limit)             |
| `SQUIRE_CC_WINDOW_MIN`    | `30`      | Window duration in minutes                              |

### Homologation

| Variable                | Default | Effect                                                          |
| ----------------------- | ------- | --------------------------------------------------------------- |
| `SQUIRE_MAX_HOMOLOG`    | `5`     | Max rounds per task (default — override in `tasks.json`)        |
| `SQUIRE_LOOP_DETECT`    | `3`     | Consecutive rejections with same pattern → forced escalation    |
| `SQUIRE_NO_PROGRESS`    | `3`     | Cycles without modified files → forced escalation               |
| `SQUIRE_IMPLEMENT_TIMEOUT` | `600` | implement_directly timeout (s) (escalation/fix)                 |

### Command queue / agent

| Variable                  | Default                       | Effect                                                       |
| ------------------------- | ----------------------------- | ------------------------------------------------------------ |
| `SQUIRE_COMMAND_TTL_H`    | `24`                          | Hours until results in `commands/done/` are deleted          |
| `SQUIRE_COMMAND_TIMEOUT`  | `900`                         | Execution timeout (s) for a queued command                   |
| `SQUIRE_AGENT_POLL`       | `2`                           | `squire agent` polling interval (s)                          |
| `SQUIRE_AGENT_REPO_ROOT`  | `/home/ai-debian/projects`    | Allowed root for `repo_path` of projects created via queue   |

### Session and lock

| Variable                | Default | Effect                                                              |
| ----------------------- | ------- | ------------------------------------------------------------------- |
| `SQUIRE_LOCK_TTL`       | `60`    | Session lock TTL (minutes). Heartbeat renews during operation.      |
| `SQUIRE_HEARTBEAT`      | `300`   | Heartbeat interval (s) (renews lock + writes checkpoint)            |

### Budget / cost

| Variable                       | Default | Effect                                                              |
| ------------------------------ | ------- | ------------------------------------------------------------------- |
| `SQUIRE_DAILY_USD_BUDGET`      | `0`     | Global daily USD cap (0 = no limit)                                 |
| `SQUIRE_PER_TASK_USD_CAP`      | `0`     | Default per-task USD cap (`Task.max_usd` overrides)                 |
| `SQUIRE_ESTIMATED_CALL_USD`    | `0.05`  | Estimated call cost before knowing the real one (used in `can_afford`) |

See [Cost and Budget](cost-and-budget.md) for the complete system.

## Configuration files

### `$SQUIRE_STATE_ROOT/budget.json`

Persisted by `squire budget set`. Env vars take precedence.

```json
{
  "daily_usd": 10.0,
  "per_task_usd": 2.0
}
```

### `$SQUIRE_STATE_ROOT/projects/<id>/project.json`

Project metadata. Schema: [`models.Project`](../../models.py).

```json
{
  "id": "squire-dashboard",
  "name": "Squire Dashboard",
  "description": "Next.js panel showing squire project state",
  "repo_path": "/home/ai-debian/squire-dashboard",
  "stack": ["typescript", "nextjs", "tailwind"],
  "status": "implementing",
  "created_at": "2026-03-24T18:32:00Z",
  "updated_at": "2026-05-11T14:24:33Z",
  "current_task_id": "task-004",
  "coding_backend": "opencode"
}
```

- `coding_backend` — overrides `SQUIRE_CODING_BACKEND` for this project.
  Valid: `"litellm"`, `"opencode"`, `"crush"`.
- `repo_path` — absolute path to the code repo. Auto-snapshot and
  auto-commit operate here.
- `stack` — informational (no behavior effect yet; future: hint for the
  mechanical gate).
- `current_task_id` — updated by squire as the cursor advances.

### `$SQUIRE_STATE_ROOT/projects/<id>/tasks.json`

Backlog. Complete schema in [Tasks](tasks.md).

### `$SQUIRE_STATE_ROOT/projects/<id>/checkpoint.json`

Persisted after every state transition. Don't edit manually — use
`squire reset` or `squire unblock` to mess with the cursor. Schema:
[`models.Checkpoint`](../../models.py).

### `$SQUIRE_STATE_ROOT/global-stats.json`

Aggregated daily counters. Auto-reset when UTC day rolls.

```json
{
  "daily_claude_code_calls": 14,
  "daily_local_llm_calls": 287,
  "date": "2026-05-11",
  "cost_estimate_usd": 1.247,
  "daily_tokens": 24381,
  "cost_by_model": {
    "claude-opus-4-7": 1.247,
    "journal-synth": 0.0
  },
  "daily_calls_unknown_cost": 0,
  "projects_touched_today": ["squire-dashboard"],
  "tasks_completed_today": 4,
  "tasks_homologated_today": 4,
  "tasks_approved_first_try_today": 3,
  "approval_first_try_rate": 75.0
}
```

`approval_first_try_rate` is the percentage (0–100) of tasks approved on
the 1st homologation among those homologated today
(`tasks_approved_first_try_today / tasks_homologated_today`). Tasks with
`skip_homologation` count in `tasks_completed_today` but stay out of the
rate — they're auto-approved and would inflate the number.

Reset with `squire budget reset`.

### `$SQUIRE_STATE_ROOT/alerts.json`

List of alerts (warnings / criticals) needing human attention.
Auto-populated by squire in cases like: task hit `max_homologation_attempts`,
per-task budget exceeded, lock corruption.

### `.env.example` (repo root)

Env var template for you to copy to `.env`. The `squire` bash wrapper
automatically `source`s `.env` at startup; use guarded exports
(`export VAR="${VAR:-value}"`) so variables already exported in the shell
take precedence over the file:

```bash
# Required
SQUIRE_STATE_ROOT=/home/ai-debian/squire-state

# Optional (defaults shown)
# SQUIRE_LITELLM_URL=http://localhost:4000/v1
# SQUIRE_LITELLM_MODEL=journal-synth
# SQUIRE_CODING_BACKEND=opencode

# Budget (recommended in production)
# SQUIRE_DAILY_USD_BUDGET=10.0
# SQUIRE_PER_TASK_USD_CAP=2.0
```

## Paths and directories

Full `$SQUIRE_STATE_ROOT/` layout:

```text
$SQUIRE_STATE_ROOT/
├── session.lock                  ← global lock
├── budget.json                   ← persisted USD caps
├── global-stats.json             ← daily counters
├── alerts.json                   ← active alerts
├── rate.json                     ← legacy, currently unused
└── projects/
    └── <project-id>/
        ├── project.json
        ├── tasks.json
        ├── checkpoint.json
        ├── history.json
        └── progress.txt          ← long-term memory
```

In production (on Unraid), typical `STATE_ROOT` is `/mnt/user/data/squire/`
(mounted volume). In dev, any writable directory works.

## Price table

The `MODEL_PRICING_PER_1M` table in [`config.py:111`](../../config.py) maps
model names to `(USD/1M input tokens, USD/1M output tokens)`. Defaults
reflect Anthropic's public pricing as of 2026-Q1:

| Model                 | Input ($/1M)  | Output ($/1M) |
| --------------------- | ------------- | ------------- |
| `claude-opus-4-7`     | 15.00         | 75.00         |
| `claude-opus-4-6`     | 15.00         | 75.00         |
| `claude-sonnet-4-6`   | 3.00          | 15.00         |
| `claude-sonnet-4-5`   | 3.00          | 15.00         |
| `claude-haiku-4-5`    | 1.00          | 5.00          |
| `journal-synth`       | 0.00          | 0.00          |

**To extend:** edit the dict in `config.py` directly. No per-model env
var (bad UX with 20+ vars). Matching is exact with prefix-match fallback —
e.g., `claude-opus-4-7[1m]` matches `claude-opus-4-7` via the prefix rule.

Unknown models cost `(0, 0)` — squire still records tokens but treats as
free. If Claude Code reports `total_cost_usd` in JSON, that value takes
precedence over the table computation
([`homologator.py:_extract_usage_from_claude_json`](../../homologator.py)).

## Further reading

- [Cost and Budget](cost-and-budget.md) — how the daily/per-task USD cap works
- [State and Recovery](state-and-recovery.md) — format and purpose of each JSON
- [CLI](cli.md) — commands that read/write these configs
