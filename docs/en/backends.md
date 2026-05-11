# Backends

[🇧🇷 Português](../backends.md) · 🇬🇧 English

Squire delegates code execution to a **backend** — an adapter that takes
a text instruction and returns the modified files. Three backends are
supported today: **LiteLLM**, **OpenCode**, **Crush**. The common
interface is `CodingBackend` in [`backends.py:108`](../../backends.py).

## Table of contents

- [Comparison](#comparison)
- [LiteLLM](#litellm)
- [OpenCode](#opencode)
- [Crush](#crush)
- [Aider (deprecated)](#aider-deprecated)
- [LLM Lock](#llm-lock)
- [Choosing a backend](#choosing-a-backend)

## Comparison

| Feature                 | LiteLLM                       | OpenCode                              | Crush                          |
| ----------------------- | ----------------------------- | ------------------------------------- | ------------------------------ |
| How it runs             | HTTP API (LiteLLM gateway)    | CLI `opencode run --agent <a> -- ...` | CLI `crush run --cwd ... --yolo` |
| Agent routing           | —                             | `code` / `debug` / `terminal` / `build` | (no routing)                 |
| Applies files via       | `filepath:` fence parser      | Edits files directly                   | Edits files directly           |
| Reports token usage     | ✓ (`usage` field in response) | ✗ (`tokens_unknown=true`)              | ✗ (`tokens_unknown=true`)     |
| Typical cost            | $0 (local model)              | Dep. on provider (OPENAI_API_KEY/etc.) | Dep. on provider              |
| Default timeout         | 1200s (`SQUIRE_INNER_TIMEOUT`)| 1200s                                  | 1200s                          |
| Setup required          | Running LiteLLM gateway       | `opencode` on PATH + API key           | `crush` on PATH                |
| ANSI on stdout          | —                             | —                                      | Stripped via regex             |
| Stdin for prompt        | (N/A — HTTP)                  | (via `-- "<prompt>"`)                  | ✓ (avoids ARG_MAX)             |

## LiteLLM

Backend that calls an LLM via OpenAI-compatible HTTP. In Squire's default
setup, it's the LiteLLM gateway on Zordon exposing the local Qwen 35B.

### How it works

[`backends.LiteLLMBackend`](../../backends.py):

1. Builds payload with `system_prompt` + user instruction
2. POST to `{base_url}/chat/completions` with retry on network failures
   (5/10/20s backoff)
3. Reads `choices[0].message.content` and (if present) `reasoning_content`
   (Qwen3 with `--reasoning-budget` returns separate chain-of-thought)
4. Parses the text looking for markdown fences and writes files:

```text
```filepath:src/foo.ts
// complete file contents
```
```

5. Extracts `usage.{prompt,completion}_tokens` from the response and
   populates `TokenUsage` with cost computed via the price table

### Accepted fence formats

`_extract_filepath` ([`backends.py:278`](../../backends.py)) recognizes
four formats:

```text
```filepath:src/foo.ts        # recommended pattern
```typescript:src/foo.ts      # Qwen alternative
src/foo.ts                    # path on line BEFORE fence
```typescript
```Dockerfile                 # known files without extension
```

### System prompt

Hardcoded in [`backends.py:30`](../../backends.py):

```text
Você é um desenvolvedor experiente num loop de CI automatizado.
O código que você escrever será compilado e testado imediatamente.
Retorne arquivos completos usando o formato ```filepath:caminho/arquivo.ext
(sem texto fora dos blocos de código, sem TODOs, sem esqueletos).
Implemente funcionalidade completa e funcional.
```

> Note: the system prompt is in Portuguese because the LLM responds in
> the language of the prompt. Override programmatically if you need
> something different.

### When to use

- Local LLM running (Zordon + dedicated GPU)
- You want $0 per-call cost and full privacy
- The local model is capable for the project's medium complexity
- You want full instrumentation (visible tokens)

> **Insight — fixed system prompt.**
> LiteLLM backend doesn't accept per-task `system_prompt`. Output style
> is uniform — squire relies on it to parse files. If you need different
> behavior, instantiate `LiteLLMBackend(system_prompt=...)` programmatically,
> but keep in mind that the fence parser depends on the declared format.

## OpenCode

Backend that delegates to the [opencode](https://opencode.ai) CLI.
Instead of parsing output and writing files, `opencode` edits the
filesystem directly. Squire detects changes via `git diff --name-only`.

### How it works

[`backends.OpenCodeBackend`](../../backends.py):

1. Selects a specialized agent (see below)
2. Invokes `opencode run --agent <agent> -- "<prompt>"` with project's
   `cwd`
3. After completion, reads modified files via `git diff` +
   `git ls-files --others`
4. Filters to source files (excludes `node_modules`, `dist`, etc.)
5. Marks `usage.tokens_unknown=True` (CLI doesn't expose counters)

### Agent routing

`_select_agent` ([`backends.py:338`](../../backends.py)) picks between:

| Agent      | Trigger                                                                                                     |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| `debug`    | `last_error` contains real stack trace marker (`traceback`, `error:`, `TypeError`, `at `, etc.)            |
| `terminal` | Task title BEGINS with operational verb: `run`, `migrate`, `seed`, `init`, `deploy`, `start`, `stop`       |
| `build`    | Title EXACTLY in allow-list: `"scaffold project"`, `"setup project"`, `"configure ci"`, etc.                |
| `debug` (fallback) | `attempts >= 6` (LLM stuck without clear error — uses debugger as last resort)                   |
| `code`     | Default — for any feature implementation                                                                    |

> **Insight — anti-false-positives.**
> The original `_select_agent` used substring matching ("fix" anywhere
> in title → `debug`, "check" → `terminal`). Result: "getCheckpoint"
> became `terminal`, any task with "fix" became `debug`. Current version
> requires **real** stack trace markers, title **beginning** for
> operational verbs, or exact match for build tasks. Bug history in
> `squire_feedback_session_2026-03-29.md`.

### When to use

- Project uses stack (TypeScript, Python, Go) opencode already knows
- You have `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (opencode uses
  external providers underneath)
- You want specialized agents per situation (debug vs implementation)
- Provider cost is acceptable

> **Remark — `tokens_unknown` doesn't mean free.**
> `opencode` calls paid providers underneath. Squire shows `$0.000` +
> `⚠ tokens_unknown`. Check the bill on the provider's console.

## Crush

Backend that delegates to the [crush](https://github.com/charmbracelet/crush)
CLI. Similar to OpenCode but without agent routing — simpler and more
predictable.

### How it works

[`backends.CrushBackend`](../../backends.py):

1. Invokes `crush run --cwd <project> --quiet --yolo` with prompt via stdin
2. Strips ANSI escape codes from stdout
3. Detects modified files via `git diff` + `git ls-files --others`
4. Marks `usage.tokens_unknown=True`

The `--yolo` flag disables interactive confirmation prompts (crush executes
directly). `--quiet` reduces decorative output. Prompt via stdin
(`input=instruction` in `subprocess.run`) avoids the kernel's ARG_MAX
limit for long prompts.

### When to use

- You want predictable behavior with no agent routing (`agent_used`
  is always `"crush"`)
- Crush's single agent is sufficient for the project
- You want a simpler backend to debug opencode issues

## Aider (deprecated)

`AiderBackend` was discontinued on 2026-03-29. Attempts to use
`squire new --backend aider` or `create_backend("aider")` raise:

```text
ValueError: Backend 'aider' foi descontinuado (2026-03-29).
Use 'opencode' ou 'litellm'.
Motivo: aider sobrescreveu tsconfig.json, criou artefatos .js e
oscilou sem convergir em sessão real.
```

The `SQUIRE_AIDER_BIN` variable still exists in `config.py` for old
checkpoint backward-compat, but has no effect.

> **Remark — why I deprecated aider.**
> In a real session, aider overwrote `tsconfig.json` with incompatible
> defaults, created `.js` artifacts beside `.ts` files, and oscillated
> between two implementations without converging after 12 rounds. Opencode
> + crush didn't show any of those patterns. Details in the 2026-03-29
> feedback session (commit `1d4a9b5`).

## LLM Lock

All backends acquire an `_LLMLock` before invoking the model:

```python
class _LLMLock:
    """Context manager que adquire um flock exclusivo antes de chamar o LLM."""
    # ...
```

[`backends.py:75`](../../backends.py). It's an exclusive `flock` on
`$SQUIRE_STATE_ROOT/llm.lock`. Guarantees that **only one backend calls
an LLM at a time** — prevents CPU/GPU saturation when multiple tools
run together (e.g., orchestrator + a standalone aider + interactive
opencode).

Parallel calls simply wait for the lock. No timeout (intentional —
better wait than fail).

## Choosing a backend

### Per project

In `project.json`:

```json
{
  "id": "my-app",
  "coding_backend": "opencode"
}
```

Overrides `SQUIRE_CODING_BACKEND` for this project.

### Globally

Env var:

```bash
export SQUIRE_CODING_BACKEND=litellm   # global default
```

### Switching mid-project

Edit `project.json`. Squire re-reads on each session. No migration needed
— `BackendResult` is uniform.

### Quick heuristic

- **Start with `opencode`** — squire uses it as default. Works out of
  the box if you already have API keys configured in your shell.
- **Switch to `litellm`** if you want $0 cost and have the LiteLLM
  gateway running locally.
- **Switch to `crush`** if opencode picks wrong agents too often for
  your task type (or you're debugging the routing).

## Further reading

- [Configuration](configuration.md) — backend-related env vars
- [Architecture](architecture.md) — where the backend sits in the overall flow
- [Cost and Budget](cost-and-budget.md) — `tokens_unknown` in detail
- [Tasks: effort](tasks.md#effort-and-model-routing) — `effort` controls
  which model LiteLLM uses
