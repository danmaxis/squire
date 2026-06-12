# State and Recovery

[🇧🇷 Português](../estado-e-recuperacao.md) · 🇬🇧 English

Squire treats the filesystem as externalized memory — nothing important
lives only in memory. This page covers JSON layout, how the lock works,
and every recovery path after crashes, blocks, or changes of mind.

## Table of contents

- [STATE_ROOT layout](#state_root-layout)
- [Per-project files](#per-project-files)
- [Atomic writes](#atomic-writes)
- [Session lock](#session-lock)
- [Auto-snapshot and auto-commit](#auto-snapshot-and-auto-commit)
- [Recovery paths](#recovery-paths)
- [Common scenarios](#common-scenarios)

## STATE_ROOT layout

```text
$SQUIRE_STATE_ROOT/
├── session.lock                  ← global lock (PID + TTL)
├── budget.json                   ← persisted USD caps
├── global-stats.json             ← aggregated daily counters
├── alerts.json                   ← alerts needing attention
├── rate.json                     ← legacy, currently unused
├── commands/                     ← dashboard → squire agent queue
│   ├── pending/<uuid>.json       ← enqueued by the dashboard
│   ├── running/<uuid>.json       ← claimed by the agent (atomic rename)
│   └── done/<uuid>.json          ← result (expires after SQUIRE_COMMAND_TTL_H)
└── projects/
    └── <project-id>/
        ├── project.json          ← project metadata
        ├── tasks.json            ← backlog
        ├── checkpoint.json       ← cursor + recovery hints + rate state
        ├── history.json          ← append-only event log
        ├── commits.json          ← commit log (always present)
        ├── homologation_log.json ← full verdicts (cap 50/task)
        └── progress.txt          ← long-term memory (free text)
```

## Per-project files

### `project.json` — metadata

Pydantic: [`models.Project`](../../models.py).

```json
{
  "id": "squire-dashboard",
  "name": "Squire Dashboard",
  "description": "Next.js panel showing squire project state",
  "repo_path": "/home/ai-debian/squire-dashboard",
  "stack": ["typescript", "nextjs"],
  "status": "implementing",
  "created_at": "2026-03-24T18:32:00Z",
  "updated_at": "2026-05-11T14:24:33Z",
  "current_task_id": "task-004",
  "coding_backend": "opencode"
}
```

### `tasks.json` — backlog

Schema in [Tasks](tasks.md). Careful when editing manually: squire writes
back after every state transition, so edits during an active session may
be overwritten.

### `checkpoint.json` — cursor + recovery

Pydantic: [`models.Checkpoint`](../../models.py).

```json
{
  "version": 1,
  "session_id": "sess-20260511-1422-a3f4c1",
  "phase": "implementing",
  "started_at": "2026-05-11T14:22:01Z",
  "last_heartbeat": "2026-05-11T14:27:01Z",
  "cursor": {
    "current_task_id": "task-004",
    "current_subtask_id": null,
    "step": "homologation",
    "attempt": 2,
    "homologation_attempt": 1
  },
  "llm_context": {
    "last_instruction": "...",
    "files_touched": ["src/components/Timeline.tsx"],
    "last_error": null,
    "tests_passing": 8,
    "tests_failing": 0,
    "test_summary": "..."
  },
  "rate_limit": {
    "claude_code_calls_this_window": 3,
    "window_started_at": "2026-05-11T14:22:01Z",
    "window_duration_minutes": 30,
    "max_calls_per_window": 10,
    "max_daily_usd": 10.0,
    "daily_cost_usd": 1.247,
    "daily_cost_date": "2026-05-11"
  },
  "recovery": {
    "can_resume": true,
    "resume_action": "continue",
    "blocked_reason": null,
    "escalation_needed": false
  }
}
```

> **Insight — checkpoint after every transition.**
> Inference is the expensive part. If squire crashes between "tests
> passed" and "homologation sent", restarting from zero burns budget.
> Persisting after every step ([`squire._save_state`](../../squire.py))
> makes `squire resume` lose at most one call.

### `history.json` — session events

Append-only. Each event is a `HistoryEvent`
([`models.py:143`](../../models.py)):

```json
{
  "events": [
    {"timestamp": "2026-05-11T14:22:01Z", "type": "session_started", "summary": "..."},
    {"timestamp": "2026-05-11T14:22:08Z", "type": "task_started", "task_id": "task-001", "summary": "Setup..."},
    {"timestamp": "2026-05-11T14:24:33Z", "type": "tests_passed", "task_id": "task-001", "attempt": 1},
    {"timestamp": "2026-05-11T14:25:00Z", "type": "homologation_approved", "task_id": "task-001"},
    {"timestamp": "2026-05-11T14:25:00Z", "type": "task_completed", "task_id": "task-001"}
  ]
}
```

Types in [`models.EventType`](../../models.py). Useful for audit,
`progress.txt` generation, and (future) live dashboard via JSONL.

### `commits.json` — project commit log

Pydantic: [`models.CommitLog`](../../models.py). Rebuilt from the
project repo's `git log` by
[`Squire._refresh_commits_json`](../../squire.py) at the start of every
session and after each completed task. The dashboard reads this file
instead of shelling out to `git log` at runtime.

```json
{
  "commits": [
    {
      "sha": "ab4432c…",
      "message": "docs: note dashboard as second writer",
      "timestamp": "2026-05-11T14:24:33Z",
      "diff_summary": "1 file(s) changed",
      "files_changed": ["docs/arquitetura.md"]
    }
  ],
  "error": null
}
```

**Always written**, even on failure — the dashboard relies on this to
distinguish "project with no commits yet" from "file disappeared":

- Success (including 0 commits): `{"commits": [...], "error": null}`
- `git log` failed (repo with no `.git`, command stuck, etc):
  `{"commits": [], "error": "git log falhou: <stderr>"}`

Consumers should treat `error != null` as a provisioning error, not an
empty list.

### `progress.txt` — long-term memory

Free text generated by [`progress.py`](../../progress.py) after each
completed task. Summarizes attempts, last error, and homologation
feedback. It's fed back into the inner loop prompt as historical context
("learning from previous iterations"), Ralph Loop pattern.

```text
# progress.txt — accumulated iteration memory
# Auto-generated by squire. Do not edit manually.

[task-001] Setup Next.js scaffolding
  Attempts: 3 | Rejections: 0
  Last error: TypeScript: src/app/layout.tsx:5:23 - Cannot find module 'fonts'

[task-002] Add fixture data loaders
  Attempts: 2 | Rejections: 1
  Last error: AssertionError: expected 11 projects, got 10
  Homologation feedback: Missing timeout handling in fetch
```

## Atomic writes

Every write uses the **write-temp-then-rename** pattern
([`checkpoint.atomic_write_json`](../../checkpoint.py)):

```python
def atomic_write_json(path: Path, data: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, str(path))  # ← atomic on same filesystem
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

Guarantees:

- **Crash mid-write** → original file intact, just an orphan `.tmp` in
  the directory.
- **Crash between `write` and `rename`** → same: original intact.
- **Crash during `rename`** → `os.replace` is atomic on the same
  filesystem; either destination has new content, or old.

> **Remark — `os.replace` is only atomic on the same filesystem.**
> If `$SQUIRE_STATE_ROOT` is on a different filesystem than `/tmp` or
> `tempfile.mkstemp` default, this fails. The code passes
> `dir=path.parent` to ensure `.tmp` lives on the same FS as the
> destination. Don't change this without understanding the guarantees.

## Session lock

Only one squire session per installation at a time. The lock is a JSON
file at `$SQUIRE_STATE_ROOT/session.lock`:

```json
{
  "holder": "sess-20260511-1422-a3f4c1",
  "project_id": "squire-dashboard",
  "acquired_at": "2026-05-11T14:22:01Z",
  "ttl_minutes": 60,
  "pid": 28471
}
```

> `project_id` is the structured identifier of the project holding the
> lock. External consumers (dashboard, inspection tools) must match
> against this field exactly — **never** substring-match `holder`, which
> collides on prefixes (e.g. a lock on `proj-happy` blocking writes to
> `proj`). May be `null` for locks written before this field existed.

### Acquisition

`acquire_lock(session_id, project_id=None)` ([`checkpoint.py:119`](../../checkpoint.py)):

1. If doesn't exist → create and return `True`
2. If exists and `holder == session_id` → renew and return `True` (reentrant)
3. If exists and `holder != session_id`:
   - Still within TTL → return `False` (another session has the lock)
   - Past TTL → take ownership (lock expired, owner probably died)

### Heartbeat

A background thread renews the lock every `SQUIRE_HEARTBEAT` seconds
(default 5min). Without heartbeat, the lock expires in 60min (default
TTL), letting a new session take ownership after silent crash.

### Release

`release_lock()` in the main loop's `finally`. If the process dies
before `finally` (SIGKILL, OOM, kernel panic), the lock stays residual
until TTL.

### Commands to manage the lock

```bash
squire status     # who's the holder + PID + alive?
squire kill       # SIGTERM the process + remove lock
squire unlock     # only remove the lock (don't kill process)
```

## Auto-snapshot and auto-commit

So the project's working tree is always recoverable, squire makes two
automatic commits:

### 1. Before each task (auto-snapshot)

`_auto_snapshot_commit` ([`squire.py:213`](../../squire.py)) runs:

```bash
git add -A
git commit -m "chore: auto-snapshot before <task-id>"
```

This ensures any uncommitted user work (or the previous task's work) is
preserved before the next agent starts. Backends like `opencode` may
`git checkout` during execution; without snapshot, real work could be
lost.

### 2. After approved homologation (auto-commit of the task)

`_commit_task_completion` ([`squire.py:260`](../../squire.py)):

```bash
git add -A
git commit -m "feat: [<task-id>] <task title>"
```

Conventional Commits-style `feat:` by default. Squire doesn't use
branches — all commits go directly to the current branch. Automatic
branching is on the roadmap (Feature #1 of the B+/A tier plan).

> **Insight — auto-commit happens BEFORE advancing.**
> The commit is what ensures the next agent doesn't discard approved
> work. Don't trust just the working tree — trust commits.

## Recovery paths

### `squire resume <project>` — resume checkpoint

The happy path. Repositions cursor at the last checkpoint and continues
from the exact step where it stopped. Works after:

- Ctrl+C (the session releases the lock before exiting)
- Process crash (lock expires after TTL, or use `squire unlock`)
- Manual pause (deliberately killing the process to do something)

### `squire unlock` — clear residual lock

When the process died but the lock still exists (and the TTL hasn't
passed). Touches nothing beyond `session.lock`.

```bash
$ squire unlock
✓ Lock removido.
```

### `squire doctor --fix` — safe lock cleanup

An alternative to `unlock` that only acts when provably safe: removes
`session.lock` only if the recorded pid is dead, and the `llm.lock` file
only if the flock is free (the residual file itself is harmless — the
real lock is the flock, not the file's existence). Locks held by living
processes are never removed.

### `squire kill` — kill process + lock

When the session is stuck and unresponsive:

```bash
$ squire kill
⚠ Encerrando PID 28471...
✓ Processo encerrado.
✓ Lock removido.
```

### `squire unblock <project> [task-id…]` — unblock tasks

Tasks with `status=blocked` (hit `max_homologation_attempts` or
`Task.max_usd`) can be resumed. Keeps already-written code in the
working tree:

```bash
$ squire unblock my-app task-007
  ✓ task-007 → pending  (Refactor auth middleware)
1 task(s) desbloqueada(s).
```

Clears `rejection_summaries` and `no_progress_streak` to prevent
immediate loop-detection retriggering on next execution.

### `squire reset <project> [task-id…]` — aggressive reset

Resets tasks to `pending` **and** discards code:

```bash
$ squire reset my-app task-007
  ✓ task-007 → pending
1 task(s) resetada(s).
  ✓ checkpoint cursor resetado
⚠ Limpando git state em /home/ai-debian/projects/my-app
✓ git checkout -- . OK
```

Runs `git reset HEAD -- .` + `git checkout -- .` in `repo_path`. Use
when the current task's work has gone off the rails and you want to
start fresh from the last commit.

### `squire rm <project>` — remove project

Removes `$SQUIRE_STATE_ROOT/projects/<project>/` (all JSONs).
**Does NOT touch `repo_path`** — code on disk stays.

Mandatory double-confirm: type `<project> <NATO-word>`:

```bash
$ squire rm my-app
⚠  Remoção de projeto: my-app
   Diretório de estado: /home/ai-debian/squire-state/projects/my-app
   Repositório de código (não será removido): /home/ai-debian/projects/my-app

Para confirmar, digite exatamente: my-app foxtrot

> my-app foxtrot
✓ Projeto 'my-app' removido.
```

> **Insight — NATO word as confirmation.**
> Alpha, bravo, charlie... zulu. A random word from the NATO phonetic
> alphabet is enough to prevent accidental `rm` from clipboard or shell
> autocompletion — you have to read the prompt to know which word to
> type. See [`squire.py:1275`](../../squire.py).

## Common scenarios

### "My squire crashed mid-task — what now?"

```bash
# 1. Check state
$ squire status
=== Estado do squire ===
⚠ Lock residual (processo morto): sess-20260511-1422-a3f4c1
=== Projetos ===
  my-app  status=implementing  tasks=4/11
=== Rate limit ===
  my-app: 3/10 calls  (janela reseta em 18.4min)

# 2. Clear the lock
$ squire unlock
✓ Lock removido.

# 3. Resume
$ squire resume my-app
→ Retomando 'my-app' do checkpoint...
[14:35:12] → session_resumed
[14:35:12] → Cursor: task-004, step=homologation, attempt 2/5
```

### "A task is blocked — how to choose between unblock and reset?"

```bash
# Inspect what happened
$ cat $SQUIRE_STATE_ROOT/projects/my-app/history.json | jq '.events[-10:]'
# Look at the last events. Find homologation_failed with summary.

# If code is almost right, just missed a correction:
$ squire unblock my-app <task-id>     # keep code, restart rounds

# If code is corrupted / heading wrong direction:
$ squire reset my-app <task-id>       # discard code, restart from prev commit
```

### "I ran `squire kill` but a zombie process remains"

Rare. Try:

```bash
$ pgrep -f "squire.py"  # check real PID
$ kill -9 <pid>          # direct SIGKILL
$ squire unlock          # clear lock
```

### "I edited `tasks.json` during an active session — my edit disappeared"

Likely: squire did `save_tasks` after your edit, overwriting. Safe workflow:

```bash
$ squire kill       # or Ctrl+C in the session
$ nano $SQUIRE_STATE_ROOT/projects/my-app/tasks.json
$ squire resume my-app
```

## Further reading

- [CLI: control commands](cli.md#control) — `kill`, `unlock`
- [CLI: recovery commands](cli.md#recovery) — `unblock`, `reset`
- [Tasks](tasks.md) — `tasks.json` schema
- [Cost and Budget](cost-and-budget.md) — recovery from USD cap exhaustion
