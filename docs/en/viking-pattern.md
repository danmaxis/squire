# Viking Pattern

[🇧🇷 Português](../padrao-viking.md) · 🇬🇧 English

The **Viking Pattern** is a simple mechanism for injecting **per-domain
restrictions** into every squire call for a project: linting, database
patterns, style conventions, project-specific prohibitions. You write
rules as Markdown files inside the project's repo; squire loads them
automatically.

## Table of contents

- [How it works](#how-it-works)
- [Repo structure](#repo-structure)
- [When it's injected](#when-its-injected)
- [Limits](#limits)
- [Examples](#examples)
- [Insights and remarks](#insights-and-remarks)

## How it works

[`viking.py`](../../viking.py) — entire implementation in ~90 lines.

`load_viking_context(project_repo_path)` looks for
`<repo>/docs/viking/*.md`, concatenates, and returns as a text block.
Squire (inner loop and homologator) injects that block into the prompt
before each relevant call:

```python
# inner_loop.py:245
try:
    import viking as _viking
    viking_ctx = _viking.load_viking_context(self.project_path)
    if viking_ctx.strip():
        parts.extend(["", "## Restrições de domínio (Padrão Viking)", viking_ctx])
except Exception:
    pass
```

Same injection in `homologator._build_review_prompt`. Claude and the
local LLM see the same rules.

## Repo structure

Inside the project's `repo_path` (not in STATE_ROOT):

```text
<repo_path>/
└── docs/
    └── viking/
        ├── stack_python.md       ← typing, style rules
        ├── database.md           ← SQL patterns, migrations
        ├── api_design.md         ← REST/GraphQL conventions
        └── (other domains)
```

Filenames are free — squire loads all `*.md` alphabetically.

## When it's injected

| Path                                     | Injects? |
| ---------------------------------------- | -------- |
| Inner loop — instruction to the backend  | ✓        |
| Homologator — Claude review prompt       | ✓        |
| Escalation `unblock` / `implement_directly` | Indirect (gets via context, doesn't re-read viking) |
| RED phase (test writing)                 | Not currently — future |
| `squire tasks plan`                      | No — plan doesn't access the repo |

## Limits

`max_chars` (default 3000) protects against giant prompts. When exceeded,
squire **truncates the last file** (not the prior ones) and adds `…` to
signal truncation.

```python
# viking.py:66
if total + len(block) > max_chars:
    remaining = max_chars - total - len(header) - 2
    if remaining > 100:
        parts.append(f"{header}\n{content[:remaining]}…")
    break
```

> **Remark — order matters.**
> Since the last file can be truncated, **put the most important first**
> (alphabetically). For example, prefix critical files with `00-`, `01-`:
> ```text
> docs/viking/
> ├── 00-prohibitions.md    ← always read, complete
> ├── 01-style_guide.md     ← always read, complete
> └── nice_to_have.md       ← may be truncated
> ```

## Examples

### `docs/viking/stack_python.md`

```markdown
# Python Stack — rules

- Python 3.11+ required.
- `from __future__ import annotations` at the top of EVERY .py file.
- Type hints on all public functions (module-level and classes).
- Don't use `Optional[X]` — use `X | None` (PEP 604).
- Pydantic v2 for schemas (not v1).
- `pytest` for tests, no `unittest`.
- f-strings for formatting. Never `%`-formatting or `.format()`.
- Imports organized: stdlib, third-party, local — separated by blank line.
- Lines up to 100 chars (not 79).
- No classes when a function will do.
```

### `docs/viking/database.md`

```markdown
# Database — rules

- Postgres 15+. No MySQL.
- Migrations via Alembic, never inline DDL in application code.
- Sequential integer IDs (BIGSERIAL), not UUID.
- Every table has `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.
- Every table has `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` + update trigger.
- Soft delete via `deleted_at TIMESTAMPTZ NULL`, NEVER physical `DELETE`.
- FKs always `ON DELETE RESTRICT` (we want to know if something depends).
- Indexes named explicitly: `idx_<table>_<columns>`.

FORBIDDEN:
- `SELECT *` in production (use explicit columns).
- `JOIN` without alias.
- ORM lazy loading without N+1 check.
```

### `docs/viking/api_design.md`

```markdown
# API Design — REST conventions

- Path in kebab-case: `/api/users/active-sessions`, not `/api/users/activeSessions`.
- Correct HTTP verbs: POST = create, PUT = replace, PATCH = mutate, DELETE = remove.
- 2xx for success, 4xx for client error, 5xx for server error.
- 404 must have JSON body `{"error": "not_found", "message": "..."}`, NEVER HTML.
- Lists always paginated: `?page=1&per_page=20`, returning `{data, meta: {total, page, pages}}`.
- Timestamps in ISO 8601 UTC with trailing Z, NEVER epoch or local timezone.
- IDs in path when referenced, NEVER in query string.
```

## Insights and remarks

> **Insight — Viking is advisory, not enforced.**
> The pattern does NOT prevent the LLM from violating rules. It only
> puts them in the prompt. The LLM tends to respect explicit instructions,
> but can fail. The mechanical gate
> ([Homologation](homologation.md#mechanical-pre-homologation-gate))
> catches specific violations checkable with tooling (`tsc`, `cargo
> clippy`); Viking covers the **rules outside automated checkers'
> reach** — style conventions, domain-specific prohibitions, project
> historical context.

> **Insight — why does it live in the repo, not STATE_ROOT?**
> Restrictions are project property, not orchestrator property. They
> should be versioned in the project's git, evolve with the code, and
> be available even when running the project outside squire. Viking is
> just a pattern for *how to read* that folder — anyone can read
> `docs/viking/*.md` to understand the rules.

> **Insight — origin of the name.**
> "Viking" because it's a governance pattern: viking-age communities
> had *þing* (assemblies) establishing local rules before execution.
> Squire does the same: reads the rules before each call, and the LLM
> operates within them. Having a real word (not a forced acronym) helps
> make it memorable.

> **Remark — Viking is not the place for task description.**
> Put general project restrictions in Viking. Specific description of
> what to do goes in `task.description` in `tasks.json`. If you find
> yourself updating Viking for an individual feature, that content
> probably belongs in the task.

## Further reading

- [Homologation](homologation.md) — when the mechanical gate catches
  what Viking doesn't
- [Tasks](tasks.md) — where to describe task scope vs where to put
  general restrictions
- [Architecture](architecture.md) — where Viking fits in the prompt
