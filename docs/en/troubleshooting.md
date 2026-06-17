# Troubleshooting

[🇧🇷 Português](../troubleshooting.md) · 🇬🇧 English

Common problems + diagnosis + fix. Organized by observable symptom, not
root cause.

> **Start with doctor.** Before hunting the cause manually, run
> `squire doctor` — it checks the LLM endpoint, binaries, locks, and
> project sanity in one pass, and points at the fix command for the
> problems it recognizes. `squire doctor --fix` cleans up provably
> dead locks.

## Table of contents

- ["Another session is active" on startup](#another-session-is-active-on-startup)
- [Residual lock after Ctrl+C or crash](#residual-lock-after-ctrlc-or-crash)
- [Task ended up `blocked` after several rounds](#task-ended-up-blocked-after-several-rounds)
- [OpenCode picked the wrong agent](#opencode-picked-the-wrong-agent)
- ["Actual cost likely higher" in summary](#actual-cost-likely-higher-in-summary)
- [Budget exhausted and I don't want to wait until midnight UTC](#budget-exhausted-and-i-dont-want-to-wait-until-midnight-utc)
- [Tests passing but gate rejects](#tests-passing-but-gate-rejects)
- [Loop detected but doesn't escalate](#loop-detected-but-doesnt-escalate)
- [Qwen returns text outside the fences](#qwen-returns-text-outside-the-fences)
- [Session slow to start](#session-slow-to-start)
- [Auto-snapshot commit doesn't happen](#auto-snapshot-commit-doesnt-happen)

## "Another session is active" on startup

**Symptom:**

```text
$ squire run my-app
⚠ Sessão ativa (PID 28471). Use 'squire kill' para encerrar.
```

**Diagnosis:** there's already a session running, OR there's a residual
lock from a session whose process died.

**Fix:**

```bash
$ squire status      # who is the holder, PID alive?
# If PID alive and another session of yours: let it run or Ctrl+C in it
# If PID dead:
$ squire unlock      # remove only the lock
# If PID alive but stuck:
$ squire kill        # kill process + remove lock
```

## Residual lock after Ctrl+C or crash

**Symptom:** `squire status` shows "Lock residual (processo morto)".

**Diagnosis:** the process died before the `finally` that releases the
lock — SIGKILL, OOM, kernel panic, or Ctrl+C during ungraceful shutdown.

**Fix:**

```bash
$ squire unlock
✓ Lock removido.
$ squire resume my-app    # resume from checkpoint
```

> **Insight — lock TTL as fail-safe.**
> If you don't run `squire unlock`, the lock expires on its own after
> `SQUIRE_LOCK_TTL` (default 60min). A new session can then take
> ownership. Use `unlock` if you want to start immediately.

## Task ended up `blocked` after several rounds

**Symptom:**

```text
[14:35:00] ✗ Task bloqueada: task-007
```

And `alerts.json` has a `max_homologations_reached` or
`task_budget_exceeded` entry.

**Diagnosis:**

- `max_homologations_reached` → hit `max_homologation_attempts` without
  approval. Probably unresolved loop or persistent edge case.
- `task_budget_exceeded` → `Task.max_usd` (or `PER_TASK_USD_CAP`) exceeded.

**Inspect the history:**

```bash
$ cat $SQUIRE_STATE_ROOT/projects/my-app/history.json \
  | jq '[.events[] | select(.task_id == "task-007") | {ts: .timestamp, type, summary}]'
```

Look at the last `homologation_failed.summary` entries to understand
why Claude was rejecting.

**Fix:**

- If the problem is clear and you can fix it (e.g., ambiguous task
  description): edit the task and `squire unblock`:
  ```bash
  $ squire tasks edit my-app task-007
  $ squire unblock my-app task-007
  ```
- If the work is corrupted and you want to start over:
  ```bash
  $ squire reset my-app task-007    # discards code + resets
  ```
- If it was USD cap: raise the cap on the task or globally and unblock.
- After resolving, acknowledge the corresponding alert:
  ```bash
  $ squire alerts list
  $ squire alerts ack --project my-app --task task-007
  ```

## OpenCode picked the wrong agent

**Symptom:** an implementation task is using `debug` agent (or `terminal`)
and producing bizarre output.

**Diagnosis:** `_select_agent`
([`backends.py:427`](../../backends.py)) matched a rule it shouldn't.
Current rules already avoid common false positives, but the title may
be tricking the regex.

**Temporary fix:** change the task title to not match the patterns:

- `terminal` triggers when the title **begins with**
  `run|migrate|seed|init|deploy|start|stop|restart`. Rewrite:
  `"run migration"` → `"add users migration"`.
- `debug` triggers when `last_error` contains stack-trace markers.
  Can't change — that's routing foundation. If inappropriate, switch
  backend to `crush` (no routing).

**Long-term fix:** open issue / PR adjusting rules in
`backends.py:_select_agent` with the new case.

## "Actual cost likely higher" in summary

**Symptom:**

```text
⚠ 3 chamada(s) sem usage reportado — custo real pode ser maior
```

**Diagnosis:** `tokens_unknown=True` in at least one call. Backends
`opencode` and `crush` don't expose token counts on stdout reliably,
so squire records `cost_usd=0` but marks the flag.

**Not a bug.** It's honesty. If you want real cost tracking for those
backends, check the provider's bill (Anthropic / OpenAI console).

**To avoid the warning:** use the `litellm` backend (which reports usage
correctly) or ignore — the flag is informational.

## Budget exhausted and I don't want to wait until midnight UTC

**Symptom:**

```text
[budget] ✗ Budget diário esgotado ($10.05/$10.00) — pausando até midnight UTC
```

**Fix:**

Option 1 — raise the cap:

```bash
$ squire budget set --daily 20
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json
  daily_usd:    $20.00
$ squire resume my-app
```

Option 2 — reset the counters (clean start, but you lose the day's
history):

```bash
$ squire budget reset
✓ Contadores diários resetados para 2026-05-11
$ squire resume my-app
```

> **Remark — `reset` wipes day history in `global-stats.json`.**
> Events in `history.json` stay intact (they have their own timestamps).
> If you need the real day total for audit, sum from events before
> resetting.

## Tests passing but gate rejects

**Symptom:** logs show "Gate pré-homologação: 1 violation(s)" even with
green tests.

**Diagnosis:** the gate runs checkers beyond tests:

- `tsc --noEmit` may catch type errors tests don't exercise
- `cargo clippy -- -D warnings` treats warnings as errors
- `go vet` detects problematic patterns
- Anti-vibe-coding detection (new `: any`, `# type: ignore`, etc.)

**Inspect the violation:** the log shows the first 120 chars of each
violation. For more detail, temporarily edit
[`squire.py`](../../squire.py) to log the full object, or run the tool
standalone:

```bash
$ cd $REPO_PATH
$ npx tsc --noEmit          # TypeScript
$ cargo clippy -- -D warnings   # Rust
$ go vet ./...              # Go
```

**Fix:** address the violation in the working tree, commit, and
`squire resume`.

## Loop detected but doesn't escalate

**Symptom:**

```text
[14:31:00] ✗ Loop detectado: mesmo erro em 3 rejeições consecutivas
[14:31:00] ⚠ Rate limit ativo — não é possível escalar agora
```

**Diagnosis:** squire detected the loop and tried to escalate to Claude
Code, but `can_afford` returned `False` — rate limit or budget full.
The loop continues because the local LLM has no way out without help.

**Fix:**

- Wait for rate limit to reset (`squire status` shows `janela reseta em
  Xmin`)
- Or if it's budget: `squire budget set --daily X` (raise) or `reset`
- Last resort: `squire kill` and edit the task description to clarify
  what's missing, then `resume`

## Qwen returns text outside the fences

**Symptom:** `files_touched` is empty even though Qwen visibly
"implemented" something in `raw_output`.

**Diagnosis:** the fence parser
(`LiteLLMBackend._apply_changes`,
[`backends.py:299`](../../backends.py)) only recognizes specific formats:

```text
```filepath:src/foo.ts
```typescript:src/foo.ts     ← language:path
src/foo.ts                   ← path on line before fence
```typescript
```

If Qwen returned only ```` ```typescript ```` with no path, or plain text
without a fence, the parser doesn't create the files.

**Fix:**

- The system prompt already instructs the format. If failing consistently,
  it's the model's fault. Consider switching to a Qwen with better
  instruction following (or a larger model).
- For a specific task, edit `description` to reinforce format with an
  example.

## Session slow to start

**Symptom:** `squire run my-app` takes ≥ 30s before the first call.

**Possible diagnoses:**

- LiteLLM gateway not responding (health-check timeout). Verify:
  `curl http://localhost:4000/v1/models`.
- Huge `tasks.json` (hundreds of tasks) — Pydantic v2 validation takes
  a few seconds.
- `STATE_ROOT` on a slow filesystem (network, NFS).
- Large `progress.txt` being read on every inner loop.

**Fix:**

- Check connectivity with LiteLLM
- If `tasks.json` is large, consider splitting into smaller projects
- If `progress.txt` is large, wait for Improvement #C of the roadmap
  (rolling summarization)

## Auto-snapshot commit doesn't happen

**Symptom:** project working tree stays dirty after a session, no
`chore: auto-snapshot before <task-id>` commit.

**Diagnosis:**

- Repo not initialized (`.git/` doesn't exist) — `_auto_snapshot_commit`
  silently returns
- Repo exists but has no commits yet (no HEAD) — also returns
- `git add` failed (permissions, hooks `.gitignore` over-excluding)

**Fix:**

```bash
$ cd $REPO_PATH
$ ls -la .git           # repo exists?
$ git log --oneline -1  # has commits?
# If both OK, run manually to see the error:
$ git add -A
$ git commit -m "chore: manual snapshot"
```

If `git commit` fails by hook, squire also fails — may be a
misconfigured hook.

## When none of this helps

- **Logs:** check `/tmp/squire.log` (bg mode) or direct terminal output
- **History:** `cat $SQUIRE_STATE_ROOT/projects/<id>/history.json | jq` —
  exact path of the last events
- **Checkpoint:**
  `cat $SQUIRE_STATE_ROOT/projects/<id>/checkpoint.json | jq` — exact
  cursor + `recovery_hints`
- **Tests:** run `pytest tests/` at squire root to ensure the code is
  healthy
- **Issues:** if none of this resolved it, open an issue with:
  - Squire version (last commit hash)
  - `squire status` output
  - Last 30 events from `history.json`
  - Expected vs observed behavior

## Further reading

- [State and Recovery](state-and-recovery.md) — detailed commands
- [Cost and Budget](cost-and-budget.md) — managing caps and refunds
- [Backends](backends.md) — behavior differences between the 3 backends
