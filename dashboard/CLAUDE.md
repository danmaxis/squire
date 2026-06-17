# CLAUDE.md — Squire Dashboard

Dashboard Next.js 14 (App Router) que visualiza e **edita** o estado do squire.
Lê arquivos JSON do filesystem; escreve alertas (ack/dismiss), tasks (CRUD),
project.json e budget direto nos arquivos (lock-checked), e enfileira
operações de host (criar projeto, run/resume/kill, planejar com Claude) em
`/data/commands/pending/` para o **agente host** (`squire agent` rodando na
VM — sem ele, essas operações ficam pendentes para sempre).

Escrita exige `Authorization: Bearer $DASHBOARD_WRITE_TOKEN` (env no
compose, valor no `.env` gitignored ao lado; sem env → 503). O usuário faz
login em `/login`; o token vai para localStorage e `authedFetch` injeta.

Deploy como container Docker **na VM Ai-Debian** via `docker compose up -d`
(porta 3101, volume rw de /home/ai-debian/squire-state, user 1000:1000) —
não no Unraid, que não enxerga o disco local da VM.

## Stack
- Next.js 14 App Router + TypeScript 5 + Tailwind CSS 3
- Vitest + @testing-library/react para testes
- Server Components por padrão (sem `use client` a menos que necessário)

## Contrato de dados — squire Python models

Os JSONs escritos pelo squire devem ser lidos com estes tipos TypeScript (ver src/lib/types.ts):

**Enums (string literals):**
- ProjectStatus: 'planning' | 'implementing' | 'reviewing' | 'blocked' | 'completed'
- TaskStatus: 'pending' | 'implementing' | 'testing' | 'homologating' | 'completed' | 'blocked'
- CursorStep: 'planning' | 'red_phase' | 'llm_execution' | 'testing' | 'homologation' | 'completed'
- Effort: 'low' | 'medium' | 'high'
- TestAuthor: 'claude' | 'local'
- EventType: 'task_started' | 'implementation_cycle' | 'tests_passed' | 'tests_failed' | 'homologation_requested' | 'homologation_approved' | 'homologation_failed' | 'escalation_created' | 'task_completed' | 'session_started' | 'session_resumed' | 'session_ended'
- AlertSeverity: 'warning' | 'critical'
- Actor: 'local_llm' | 'claude_code' | 'squire' | 'human'

**JSON file structure:**
```
{DATA_PATH}/global-stats.json        → GlobalStats (snake_case fields)
{DATA_PATH}/alerts.json              → { "alerts": Alert[] }   ← AlertList WRAPPER
{DATA_PATH}/projects/{id}/project.json  → Project
{DATA_PATH}/projects/{id}/tasks.json    → { "tasks": Task[] }  ← TaskList WRAPPER
{DATA_PATH}/projects/{id}/history.json  → { "events": HistoryEvent[] } ← History WRAPPER
{DATA_PATH}/projects/{id}/checkpoint.json → Checkpoint
{DATA_PATH}/projects/{id}/commits.json   → { "commits": CommitSummary[] } ← CommitLog WRAPPER
```

**KEY GlobalStats fields (snake_case, not camelCase):**
- daily_claude_code_calls, daily_local_llm_calls, cost_estimate_usd
- tasks_completed_today, approval_first_try_rate, date, projects_touched_today

**Dev data path:** `process.env.SQUIRE_DATA_PATH ?? path.join(cwd, 'fixtures', 'data')`

## Componentes implementados

- `ProjectCard` — card de projeto com barra de progresso
- `AlertBanner` — banner fixo no topo com alertas critical/warning
- `GlobalStats` — 5 cards de métricas (server component, aceita props)
- `TaskList` — lista expansível de tasks com badges de effort/TDD/rejeição
- `Timeline` — linha do tempo de HistoryEvent com cores por Actor
- `CommitLog` — histórico de commits com diff_summary
- `RefreshController` — trigger de auto-refresh (client component)
- `RateLimitGauge` — gauge de consumo do budget Claude Code
- `CheckpointPanel` — inspetor de estado da sessão (cursor + context + recovery)
- `TDDProgressBar` — visualizador das fases RED/GREEN/REFACTOR

## Checklist de homologação

Ao revisar código, verificar:
1. Todos os campos de JSON usam snake_case (não camelCase) — igual ao Python
2. AlertList/TaskList/History/CommitLog são lidos com seus wrappers (.alerts / .tasks / .events / .commits)
3. GlobalStats usa daily_claude_code_calls (não llm_calls.claude_code)
4. AlertSeverity aceita apenas 'warning' e 'critical' (não 'error' nem 'info')
5. Actor usa 'local_llm', 'claude_code', 'squire', 'human' (não 'system', 'agent', etc.)
6. Server components não usam hooks (useEffect, useState) nem 'use client'
7. Testes existem e passam (npm test)
8. Nenhum `any` no TypeScript
9. Fixtures em fixtures/data/ têm estrutura correta com wrappers

## Convenções
- Commits: conventional commits em inglês (feat: / fix: / chore:)
- Idioma da UI: português brasileiro
- Sem CSS Modules — apenas Tailwind
- Imports de tipos de '@/lib/types', funções de '@/lib/data'
