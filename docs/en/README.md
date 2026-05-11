# Squire Documentation

[🇧🇷 Português](../README.md) · 🇬🇧 English

Welcome to Squire's complete documentation. For an overview and quickstart,
go back to [README.en.md](../../README.en.md) at the root.

## Concepts

Start here if it's your first time:

- **[Architecture](architecture.md)** — the two-tier model, components,
  task flow, and why the filesystem is treated as memory.
- **[Tasks](tasks.md)** — the unit of work: JSON schema, lifecycle,
  effort, TDD, RED phase, and CLI authoring workflows.
- **[Backends](backends.md)** — who actually executes code: LiteLLM (local
  HTTP), OpenCode (CLI with agent routing), Crush (simple CLI).
- **[Homologation](homologation.md)** — Claude Code's review cycle:
  mechanical gate, loop detection, technical escalation.
- **[Viking Pattern](viking-pattern.md)** — per-domain restrictions in
  `<repo>/docs/viking/*.md` injected into every call.

## Operations

For running Squire day-to-day:

- **[CLI](cli.md)** — full reference of every subcommand with examples
  and expected output.
- **[Configuration](configuration.md)** — env vars, `budget.json`,
  `project.json`, price table, paths, precedence.
- **[Cost and Budget](cost-and-budget.md)** — token/USD tracking, daily
  and per-task caps, refunds, `squire budget` commands.
- **[State and Recovery](state-and-recovery.md)** — `STATE_ROOT` layout,
  atomic writes, session lock, and every recovery path.

## Diagnostics

When something goes wrong:

- **[Troubleshooting](troubleshooting.md)** — common problems indexed by
  observable symptom, with diagnosis and step-by-step fix.

## Documentation conventions

- **Source anchors** like `file.py:line` are references to source code
  (paste in your editor, they're not clickable links).
- **Callouts** in blockquotes: `> **Insight:** …` for design rationale,
  `> **Remark:** …` for tradeoffs, GitHub alerts (`> [!WARNING]`, etc.)
  sparingly for safety-critical notes.
- **Cross-links** are relative (`[CLI](cli.md)`) — they work both on
  GitHub web and in local renderers (glow, mdcat).
- **Mermaid diagrams** render natively on GitHub.
- **PT primary** at [`../`](../) — every doc has a Portuguese version that
  is the source of truth; this English mirror tracks it 1:1.

## Roadmap

Upcoming features are documented in `/home/ai-debian/.claude/plans/`
(outside the repo, in agent state). Includes: branch + PR automation,
codebase RAG via Qdrant, structured homologation output
(file:line:severity), live dashboard via JSONL events, gate caching, and
more.
