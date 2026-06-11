# CLI

[🇧🇷 Português](../cli.md) · 🇬🇧 English

Complete reference for every `squire` subcommand. The dispatcher is the
bash script `squire` (repo root); each subcommand is a `cmd_<name>` function
there. For tasks, it delegates to `tasks_cli.py`.

> **Tip:** run `squire help` or `squire <cmd> --help` to see the in-terminal
> summary. This page is more detailed, with examples and expected output.

## Table of contents

- [Execution](#execution): `run` · `bg` · `resume` · `dry`
- [Observation](#observation): `status` · `log` · `doctor`
- [Control](#control): `kill` · `unlock`
- [Recovery](#recovery): `unblock` · `reset`
- [Alerts](#alerts): `alerts list|ack|rm`
- [Tasks](#tasks): `tasks list|add|edit|rm|split|plan`
- [Project](#project): `new` · `projects` · `rm`
- [Budget](#budget): `budget` · `budget set` · `budget reset`
- [Help](#help)

## Execution

### `squire run <project>`

Runs the main loop in foreground. Acquires the session lock, reads the
checkpoint, and processes all pending tasks in order.

| Flag       | Description                                              |
| ---------- | -------------------------------------------------------- |
| `--quiet`  | Suppress instruction/response preview (`┊` markers)      |
| `--dry-run`| Simulate without calling backends (shortcut: `squire dry`) |
| `--resume` | Resume from checkpoint (shortcut: `squire resume`)         |

**Example:**

```bash
$ squire run squire-dashboard
→ Iniciando squire para 'squire-dashboard'...
[14:22:01] → Sessão iniciada: sess-20260511-1422-a3f4c1
[14:22:01] → Projeto: Squire Dashboard (squire-dashboard)
[14:22:01] → ==================================================
[14:22:01] → Task [task-001]: Setup Next.js scaffolding
[14:22:01] → ==================================================
[14:22:01] → Inner loop: Setup Next.js scaffolding (tentativa 1/10)
...
[14:24:33] ✓ Task concluída: [task-001] Setup Next.js scaffolding ($0.045)
```

> Logs are in Portuguese — squire is a Portuguese-primary project. The
> CLI accepts the same flags regardless of language.

**See also:** [`squire bg`](#squire-bg-project), [`squire resume`](#squire-resume-project-bg), [Tasks](tasks.md).

### `squire bg <project>`

Like `run` but in background via `nohup`, with stdout redirected to
`/tmp/squire.log`. Follow with `squire log`.

```bash
$ squire bg squire-dashboard
→ Iniciando 'squire-dashboard' em background → /tmp/squire.log
✓ Rodando com PID 28471
  Acompanhe com: squire log
```

### `squire resume <project> [bg]`

Resumes an interrupted session from the checkpoint. Add `bg` to resume
in background.

```bash
$ squire resume squire-dashboard
→ Retomando 'squire-dashboard' do checkpoint...
[14:35:12] → session_resumed
[14:35:12] → Cursor: task-003, step=homologation, attempt 2/5
```

> **Remark:** if the session crashed mid-Claude-call, the checkpoint
> repositions before the mechanical gate. You don't pay for the failed
> call — `RateLimiter.refund` handles it when applicable. See
> [Cost and Budget](cost-and-budget.md#refund-on-error).

### `squire dry <project>`

Shortcut for `squire run --dry-run`. Shows what it would do without
invoking any backend or spending budget. Useful for inspecting the
cursor before resuming.

## Observation

### `squire status [<project>]`

State summary in four blocks:

1. **Active session** — lock holder, PID, or "Nenhuma sessão ativa"
2. **Projects** — for each project, status + `done/total` task count
3. **Rate limit** — calls in current window + time until reset
4. **Budget** — today's spend + configured cap + ≥75% warning flag

```bash
$ squire status
=== Estado do squire ===

✓ Sessão ativa: sess-20260511-1422-a3f4c1 (PID 28471)

=== Projetos ===
  squire-dashboard  status=implementing  tasks=4/11
  pilotinho               status=completed     tasks=8/8

=== Rate limit ===
  squire-dashboard: 3/10 calls  (janela reseta em 18.4min)

=== Budget ===
  Hoje: $1.247 / $10.00  (12% usado)  |  tokens: 24,381
```

### `squire log`

`tail -f /tmp/squire.log` — useful when running in background. Blocks
until Ctrl+C.

```bash
$ squire log
[14:42:08] → Rodada 2/5 — inner loop: [task-004] Add CommitLog component
[14:42:08] →   ┊→ ## Task: Add CommitLog component
...
```

### `squire doctor [--fix]`

Environment health check (delegated to `doctor.py`). Verifies everything
a session needs to run and prints `[ OK ]/[WARN]/[FAIL]/[INFO]` per item.
Exits with code 1 if there's any FAIL.

Checks: writable state root · LLM endpoint reachable + configured models
available · `claude` binary on PATH (+version) · binaries for backends in
use (`opencode`/`crush`) · `session.lock` (pid alive? TTL expired?) ·
`llm.lock` (flock held?) · per-project sanity (git repo, dirty working
tree, blocked tasks, dead-but-resumable session) · pending alerts ·
`global-stats.json` freshness.

```bash
$ squire doctor
squire doctor

Estado
  [ OK ] state root  /home/ai-debian/squire-state

LLM local
  [ OK ] LLM endpoint  http://192.168.50.24:11434/v1
  [ OK ] modelo 'journal-synth:latest'  disponível
...
10 ok · 1 warn · 0 fail
```

`--fix` applies only safe cleanups: removes a `session.lock` whose pid is
provably dead and the `llm.lock` file when the flock is free. It never
removes locks held by living processes.

## Control

### `squire kill`

Kills the active session's process (SIGTERM, then SIGKILL after 1s) and
removes the lock. Use when the session is stuck and not responding to Ctrl+C.

```bash
$ squire kill
⚠ Encerrando PID 28471...
✓ Processo encerrado.
✓ Lock removido.
```

> [!WARNING]
> `kill` is brutal. To stop gracefully, use Ctrl+C in the terminal where
> `squire run` is running — squire releases the lock correctly and writes
> `recovery.resume_action = "continue"` to the checkpoint, leaving
> everything ready for `squire resume`.

### `squire unlock`

Removes a residual `session.lock` left by a crash (without killing a
process). Use when `squire status` shows "Lock residual encontrado (processo morto)".

```bash
$ squire unlock
✓ Lock removido.
```

## Recovery

### `squire unblock <project> [task-id …]`

Marks `blocked` tasks (those that hit `max_homologation_attempts`) back
to `pending`. Keeps already-written code in the repo. Without `task-id`,
unblocks all blocked tasks. Clears `rejection_summaries` and
`no_progress_streak` to prevent immediate loop-detection retriggering.

```bash
$ squire unblock squire-dashboard task-005
  ✓ task-005 → pending  (Add commit log empty state)

1 task(s) desbloqueada(s).
```

**See also:** [`squire reset`](#squire-reset-project-task-id) (more aggressive, discards code).

### `squire reset <project> [task-id …]`

Resets tasks to `pending` **and** discards work with `git reset HEAD` +
`git checkout -- .` in `repo_path`. Without `task-id`, resets all tasks
in the project. Also clears the checkpoint cursor.

```bash
$ squire reset squire-dashboard task-005
  ✓ task-005 → pending  (Add commit log empty state)

1 task(s) resetada(s).
  ✓ checkpoint cursor resetado
⚠ Limpando git state em /home/ai-debian/squire-dashboard
✓ git checkout -- . OK
```

> [!WARNING]
> `reset` discards uncommitted changes in the project's working tree.
> Squire auto-commits after every approved task, so usually only the
> current task's work is lost — but confirm with `git status` in the
> repo before.

## Alerts

Subcommands delegated to `alerts_cli.py`. Alerts are generated by squire
in cases like `max_homologations_reached` and exceeded budget, and live in
`$SQUIRE_STATE_ROOT/alerts.json` until acknowledged or removed.

### `squire alerts list [--all] [--project <id>]`

Lists pending (unacknowledged) alerts with a 1-based index, severity,
project/task, age, and message. `--all` also includes acknowledged ones
(without index); `--project` filters by project.

```bash
$ squire alerts list
Alertas pendentes (2):
  1  CRIT  claw-code-study/task-026a  71d  max_homologations_reached: Task '...' falhou 5 homologações
  2  CRIT  semanario-infantil/task-009  65d  max_homologations_reached: Task '...' falhou 5 homologações
```

`squire alerts` with no subcommand is an alias for `list`.

### `squire alerts ack <n> [<n>…] | --all [--project <id>] [--task <id>]`

Marks alerts as acknowledged (`acknowledged: true` — the same field the
dashboard writes). By index (referring to the pending listing) or in bulk
with `--all`, optionally filtered by `--project`/`--task`.

```bash
$ squire alerts ack 1 2
✓ 2 alerta(s) reconhecido(s).

$ squire alerts ack --all --project semanario-infantil
✓ 4 alerta(s) reconhecido(s).
```

> [!NOTE]
> The dashboard is a second writer of `alerts.json` (POST `/api/alerts/ack`).
> Indexes can race if an alert is dismissed by the dashboard between `list`
> and `ack` — with the dashboard running, prefer the `--project`/`--task`
> selectors.

### `squire alerts rm <n> [<n>…] | --acked | --all`

Removes alerts from the file (equivalent to the dashboard's "dismiss").
`--acked` removes only acknowledged ones; `--all` clears everything.

```bash
$ squire alerts rm --acked
✓ 13 alerta(s) removido(s).
```

## Tasks

Subcommands delegated to `tasks_cli.py`. For the Task model and `tasks.json`
shape, see [Tasks](tasks.md).

### `squire tasks list <project>`

Lists tasks with visual status. Shortcut: `squire tasks <project>` (no subcommand).

```bash
$ squire tasks squire-dashboard
  ✓ [task-001] Setup Next.js scaffolding
  ✓ [task-002] Add fixture data loaders
  ⟳ [task-003] Implement ProjectCard component
  · [task-004] Implement Timeline component
  · [task-005] Implement AlertBanner component
  ...
```

Legend: `✓` completed · `⟳` implementing · `⌛` homologating · `·` pending · `✗` blocked.

### `squire tasks add <project>`

Adds a task interactively or via flags.

| Flag                    | Description                                                |
| ----------------------- | ---------------------------------------------------------- |
| `--title "..."`         | Required title                                             |
| `--desc "..."`          | Description (otherwise, opens `$EDITOR`)                   |
| `--id "..."`            | Custom ID (default: next free `task-NNN`)                  |
| `--skip-homolog`        | Auto-approve after inner loop (no Claude call)             |
| `--max N`               | `max_attempts` (default: 10)                                |
| `--max-homolog N`       | `max_homologation_attempts` (default: 5)                    |

### `squire tasks edit <project> [task-id]`

Opens the task in `$EDITOR` (editable YAML format). Without `task-id`,
opens the entire `tasks.json`.

### `squire tasks rm <project> <task-id>`

Removes the task. No double-confirm — this only touches state JSON,
easy to recover from backup or git.

### `squire tasks split <project> <task-id>`

Asks Claude to subdivide the task into subtasks. Shows the proposal and
allows one refinement before applying.

### `squire tasks plan <project> [--desc "..."]`

Asks Claude to generate an initial task list from a free-form description.
Up to 3 interactive refinement cycles. At the end, asks whether to
replace or append to the current `tasks.json`.

```bash
$ squire tasks plan squire-dashboard --desc "Next.js page reading JSON state"
[planning] Claude gerando rascunho...
[planning] 11 tasks propostas. Refinar? [y/N] n
[planning] Modo: (s)ubstituir / (a)nexar / (c)ancelar? s
✓ 11 tasks gravadas em tasks.json
```

## Project

### `squire new <project>`

Creates a new project with template `project.json` + `tasks.json` in
`STATE_ROOT/projects/<project>/`.

| Flag                  | Default                                       |
| --------------------- | --------------------------------------------- |
| `--repo <path>`       | `/home/ai-debian/projects/<project>`          |
| `--name <name>`       | `<project>` (same as the ID)                  |
| `--stack <csv>`       | `typescript`                                  |
| `--backend <name>`    | `opencode` (also accepts `litellm`, `crush`)  |

```bash
$ squire new my-api --repo /home/ai-debian/projects/my-api \
              --stack python,fastapi --backend opencode
✓ Projeto 'my-api' criado em /home/ai-debian/squire-state/projects/my-api
...
```

### `squire projects`

Lists available projects (basenames of directories in `STATE_ROOT/projects/`).

### `squire rm <project>`

Removes the project's state after **double confirmation**: you must type
`<project> <NATO-word>` (e.g., `my-api echo`) to confirm. The
`repo_path` (code on disk) is NOT touched.

```bash
$ squire rm my-api
⚠  Remoção de projeto: my-api
   Diretório de estado: /home/ai-debian/squire-state/projects/my-api
   ...
Para confirmar, digite exatamente: my-api echo

> my-api echo
✓ Projeto 'my-api' removido.
```

> **Insight:** using a NATO alphabet word (alpha, bravo, charlie, ...
> zulu) prevents accidental `rm` from clipboard or shell history — you
> have to read the prompt to know which word to type. See
> [`squire.py:1266`](../../squire.py).

## Budget

Commands related to cost tracking and USD caps. Details in
[Cost and Budget](cost-and-budget.md).

### `squire budget` (or `squire budget show`)

Shows today's spend + configured cap + per-model breakdown.

```bash
$ squire budget
=== Budget — 2026-05-11 (UTC) ===

  Spent hoje:   $1.247  (24,381 tokens)
  Daily cap:    $10.00  (12% usado)
  Restante:     $8.753
  Per-task cap: $2.00

  Por modelo:
    claude-opus-4-7: $1.247
    journal-synth: $0.000

Para configurar:
  squire budget set --daily 10 --per-task 2
```

### `squire budget set --daily X --per-task Y`

Persists USD caps in `$SQUIRE_STATE_ROOT/budget.json`. Env vars
(`SQUIRE_DAILY_USD_BUDGET`, `SQUIRE_PER_TASK_USD_CAP`) take precedence
over the file.

### `squire budget reset`

Zeros the daily counters (`global-stats.json`). Useful when you want to
restart counting without waiting for UTC rollover.

## Help

### `squire help`

Prints the summary of all commands. Aliases: `squire -h`, `squire --help`,
and `squire` (no arguments).

## Appendix — CLI environment variables

| Variable            | Default                          | Description                                          |
| ------------------- | -------------------------------- | ---------------------------------------------------- |
| `SQUIRE_STATE_ROOT` | `/home/ai-debian/squire-state`   | Persistent state root (used by all commands)         |
| `EDITOR`            | `nano`                           | Editor for `squire tasks edit`                       |

Other env vars (that affect orchestrator behavior, not the CLI itself)
are in [Configuration](configuration.md).
