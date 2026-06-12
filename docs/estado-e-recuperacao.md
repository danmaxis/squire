# Estado e recuperação

🇧🇷 Português · [🇬🇧 English](en/state-and-recovery.md)

O squire trata o filesystem como memória externalizada — nada do que importa
mora apenas em memória. Este documento explica o layout dos JSONs, como o
lock funciona, e cada caminho de recuperação após crashes, blocks, ou
mudanças de ideia.

## Sumário

- [Layout do STATE_ROOT](#layout-do-state_root)
- [Arquivos por projeto](#arquivos-por-projeto)
- [Escrita atômica](#escrita-atômica)
- [Session lock](#session-lock)
- [Auto-snapshot e auto-commit](#auto-snapshot-e-auto-commit)
- [Caminhos de recuperação](#caminhos-de-recuperação)
- [Cenários comuns](#cenários-comuns)

## Layout do STATE_ROOT

```text
$SQUIRE_STATE_ROOT/
├── session.lock                  ← lock global (PID + TTL)
├── budget.json                   ← caps USD persistidos
├── global-stats.json             ← contadores agregados do dia
├── alerts.json                   ← alertas que requerem atenção
├── rate.json                     ← legado, não usado atualmente
├── commands/                     ← fila do dashboard → squire agent
│   ├── pending/<uuid>.json       ← enfileirado pelo dashboard
│   ├── running/<uuid>.json       ← reivindicado pelo agente (rename atômico)
│   └── done/<uuid>.json          ← resultado (expira após SQUIRE_COMMAND_TTL_H)
└── projects/
    └── <project-id>/
        ├── project.json          ← metadata do projeto
        ├── tasks.json            ← backlog
        ├── checkpoint.json       ← cursor + recovery hints + rate state
        ├── history.json          ← lista append-only de eventos
        ├── commits.json          ← log de commits (sempre presente)
        └── progress.txt          ← memória de longo prazo (texto livre)
```

## Arquivos por projeto

### `project.json` — metadata

Pydantic: [`models.Project`](../models.py).

```json
{
  "id": "squire-dashboard",
  "name": "Squire Dashboard",
  "description": "Painel Next.js mostrando estado dos projetos",
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

Schema em [Tasks](tasks.md). Cuidado ao editar manualmente: o squire grava
de volta após cada transição de estado, então edições durante uma sessão
ativa podem ser sobrescritas.

### `checkpoint.json` — cursor + recovery

Pydantic: [`models.Checkpoint`](../models.py).

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

> **Insight — checkpoint depois de cada transição.**
> A inferência é a parte cara. Se o squire crashar entre "testes passaram"
> e "homologação enviada", retomar do zero queima budget. Persistir após
> cada step ([`squire._save_state`](../squire.py)) faz `squire resume`
> perder no máximo uma chamada.

### `history.json` — eventos da sessão

Append-only. Cada evento é um `HistoryEvent` ([`models.py:143`](../models.py)):

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

Tipos em [`models.EventType`](../models.py). Útil para auditoria, geração
de `progress.txt`, e (futuramente) live dashboard via JSONL.

### `commits.json` — log de commits do projeto

Pydantic: [`models.CommitLog`](../models.py). Recompilado a partir do
`git log` do repo do projeto pelo [`Squire._refresh_commits_json`](../squire.py)
no início de cada sessão e após cada task concluída. O dashboard lê este
arquivo em vez de executar `git log` em runtime.

```json
{
  "commits": [
    {
      "sha": "ab4432c…",
      "message": "docs: note dashboard as second writer",
      "timestamp": "2026-05-11T14:24:33Z",
      "diff_summary": "1 arquivo(s) alterado(s)",
      "files_changed": ["docs/arquitetura.md"]
    }
  ],
  "error": null
}
```

**Sempre escrito**, mesmo em falha — o dashboard depende disso para
distinguir "projeto sem commits ainda" de "arquivo sumiu":

- Sucesso (inclusive 0 commits): `{"commits": [...], "error": null}`
- `git log` falha (repo sem `.git`, comando travado, etc):
  `{"commits": [], "error": "git log falhou: <stderr>"}`

Consumidores devem tratar `error != null` como erro de provisionamento,
não como lista vazia.

### `progress.txt` — memória de longo prazo

Texto livre gerado por [`progress.py`](../progress.py) após cada task
concluída. Resume tentativas, último erro, e feedback de homologação.
É injetado de volta no prompt do inner loop como contexto histórico
("aprendizado de iterações anteriores"), padrão Ralph Loop.

```text
# progress.txt — memória acumulada de iterações
# Gerado automaticamente pelo squire. Não editar manualmente.

[task-001] Setup Next.js scaffolding
  Tentativas: 3 | Rejeições: 0
  Último erro: TypeScript: src/app/layout.tsx:5:23 - Cannot find module 'fonts'

[task-002] Add fixture data loaders
  Tentativas: 2 | Rejeições: 1
  Último erro: AssertionError: expected 11 projects, got 10
  Feedbacks de homologação: Falta tratar timeout no fetch
```

## Escrita atômica

Toda escrita usa o padrão **write-temp-then-rename** ([`checkpoint.atomic_write_json`](../checkpoint.py)):

```python
def atomic_write_json(path: Path, data: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, str(path))  # ← atômico no mesmo filesystem
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

Garantias:

- **Crash no meio de uma escrita** → arquivo original intacto, só tem um
  `.tmp` órfão no diretório.
- **Crash entre `write` e `rename`** → mesmo: original intacto.
- **Crash durante `rename`** → o `os.replace` é atomic no mesmo filesystem;
  ou o destino tem o conteúdo novo, ou o antigo.

> **Remark — `os.replace` só é atômico no mesmo filesystem.**
> Se `$SQUIRE_STATE_ROOT` está em um filesystem diferente do `/tmp` ou
> do `tempfile.mkstemp` default, isso falha. O código passa `dir=path.parent`
> para garantir que o `.tmp` mora no mesmo FS do destino. Não mude isso
> sem entender as garantias.

## Session lock

Apenas uma sessão squire por instalação por vez. O lock é um JSON em
`$SQUIRE_STATE_ROOT/session.lock`:

```json
{
  "holder": "sess-20260511-1422-a3f4c1",
  "project_id": "squire-dashboard",
  "acquired_at": "2026-05-11T14:22:01Z",
  "ttl_minutes": 60,
  "pid": 28471
}
```

> `project_id` é o identificador estruturado do projeto que detém o lock.
> Consumidores externos (dashboard, ferramentas de inspeção) devem fazer
> match exato contra este campo — **nunca** parsear `holder` por substring,
> que casa prefixos diferentes (ex: lock em `proj-happy` colidindo com
> `proj`). Pode vir `null` em locks antigos, gravados antes desta mudança.

### Aquisição

`acquire_lock(session_id, project_id=None)` ([`checkpoint.py:119`](../checkpoint.py)):

1. Se não existe → cria e retorna `True`
2. Se existe e `holder == session_id` → renova e retorna `True` (reentrante)
3. Se existe e `holder != session_id`:
   - Se ainda dentro do TTL → retorna `False` (outra sessão tem o lock)
   - Se passou do TTL → toma posse (lock expirou, dono provavelmente morreu)

### Heartbeat

Thread em background renova o lock a cada `SQUIRE_HEARTBEAT` segundos
(default 5min). Sem heartbeat, o lock expira em 60min (default TTL),
permitindo que uma nova sessão tome posse após crash silencioso.

### Liberação

`release_lock()` no `finally` do main loop. Se o processo morre antes
do `finally` (SIGKILL, OOM, kernel panic), o lock fica residual até o TTL.

### Comandos para mexer no lock

```bash
squire status     # mostra holder + PID + se vivo
squire kill       # SIGTERM no processo + remove lock
squire unlock     # só remove o lock (não mata processo)
```

## Auto-snapshot e auto-commit

Para que o working tree do projeto seja sempre recuperável, o squire faz
dois commits automáticos:

### 1. Antes de cada task (auto-snapshot)

`_auto_snapshot_commit` ([`squire.py:206`](../squire.py)) roda:

```bash
git add -A
git commit -m "chore: auto-snapshot before <task-id>"
```

Isso garante que qualquer trabalho não-commitado do usuário (ou da task
anterior) é preservado antes do próximo agente começar. Backends como
`opencode` podem fazer `git checkout` durante a execução; sem snapshot,
trabalho real seria perdido.

### 2. Após homologação aprovada (auto-commit da task)

`_commit_task_completion` ([`squire.py:255`](../squire.py)):

```bash
git add -A
git commit -m "feat: [<task-id>] <título da task>"
```

Mensagem com `feat:` por default (conventional commits). O squire não usa
branches — todos os commits vão direto na branch atual. Branching automático
está no roadmap (Feature #1 do plano B+/A tier).

> **Insight — auto-commit acontece ANTES de avançar.**
> O commit é o que garante que o próximo agente não vai descartar o trabalho
> aprovado. Não confie só no working tree — confie em commits.

## Caminhos de recuperação

### `squire resume <projeto>` — retomar checkpoint

O happy path. Reposiciona o cursor no último checkpoint e continua do step
exato onde parou. Funciona após:

- Ctrl+C (a sessão libera o lock antes de sair)
- Crash do processo (lock expira após TTL, ou use `squire unlock`)
- Pause manual (matar o processo deliberadamente para fazer algo)

### `squire unlock` — limpar lock residual

Quando o processo morreu mas o lock ainda existe (e o TTL não passou).
Não toca em nada além do `session.lock`.

```bash
$ squire unlock
✓ Lock removido.
```

### `squire doctor --fix` — limpeza segura de locks

Alternativa ao `unlock` que só age quando é comprovadamente seguro:
remove o `session.lock` apenas se o pid registrado está morto, e o
arquivo `llm.lock` apenas se o flock está livre (o arquivo residual em
si é inofensivo — o lock real é o flock, não a existência do arquivo).
Locks de processos vivos nunca são removidos.

### `squire kill` — matar processo + lock

Quando a sessão travou e não responde:

```bash
$ squire kill
⚠ Encerrando PID 28471...
✓ Processo encerrado.
✓ Lock removido.
```

### `squire unblock <projeto> [task-id…]` — desbloquear tasks

Tasks com `status=blocked` (atingiram `max_homologation_attempts` ou
`Task.max_usd`) podem ser retomadas. Mantém o código já escrito no
working tree:

```bash
$ squire unblock my-app task-007
  ✓ task-007 → pending  (Refator do auth middleware)
1 task(s) desbloqueada(s).
```

Limpa `rejection_summaries` e `no_progress_streak` para evitar disparo
imediato da detecção de loops na próxima execução.

### `squire reset <projeto> [task-id…]` — reset agressivo

Reseta tasks para `pending` **e** descarta código:

```bash
$ squire reset my-app task-007
  ✓ task-007 → pending
1 task(s) resetada(s).
  ✓ checkpoint cursor resetado
⚠ Limpando git state em /home/ai-debian/projects/my-app
✓ git checkout -- . OK
```

Faz `git reset HEAD -- .` + `git checkout -- .` no `repo_path`. Use quando
o trabalho da task corrente foi para um caminho sem volta e você quer
recomeçar do último commit.

### `squire rm <projeto>` — remover projeto

Remove `$SQUIRE_STATE_ROOT/projects/<projeto>/` (todos os JSONs).
**Não toca no `repo_path`** — o código no disco fica.

Confirmação dupla obrigatória: você precisa digitar `<projeto> <palavra-NATO>`:

```bash
$ squire rm my-app
⚠  Remoção de projeto: my-app
   Diretório de estado: /home/ai-debian/squire-state/projects/my-app
   Repositório de código (não será removido): /home/ai-debian/projects/my-app

Para confirmar, digite exatamente: my-app foxtrot

> my-app foxtrot
✓ Projeto 'my-app' removido.
```

> **Insight — palavra NATO como confirmação.**
> Alpha, bravo, charlie... zulu. Uma palavra aleatória do alfabeto fonético
> é o suficiente para impedir `rm` acidental por copy-paste do histórico ou
> autocompletar do shell. Veja [`squire.py:1294`](../squire.py).

## Cenários comuns

### "Meu squire crashou no meio de uma task — o que fazer?"

```bash
# 1. Verificar estado
$ squire status
=== Estado do squire ===
⚠ Lock residual (processo morto): sess-20260511-1422-a3f4c1
=== Projetos ===
  my-app  status=implementing  tasks=4/11
=== Rate limit ===
  my-app: 3/10 calls  (janela reseta em 18.4min)

# 2. Limpar o lock
$ squire unlock
✓ Lock removido.

# 3. Retomar
$ squire resume my-app
→ Retomando 'my-app' do checkpoint...
[14:35:12] → session_resumed
[14:35:12] → Cursor: task-004, step=homologation, attempt 2/5
```

### "Uma task está bloqueada — como decidir entre unblock e reset?"

```bash
# Inspecione o que aconteceu
$ cat $SQUIRE_STATE_ROOT/projects/my-app/history.json | jq '.events[-10:]'
# Veja os últimos eventos. Procure por homologation_failed com summary.

# Se o código está quase certo, só faltou alguma correção:
$ squire unblock my-app <task-id>     # mantém código, recomeça as rodadas

# Se o código está corrompido / em direção errada:
$ squire reset my-app <task-id>       # descarta código, recomeça do commit anterior
```

### "Fiz `squire kill` mas o processo zombie continua"

Raro. Tente:

```bash
$ pgrep -f "squire.py"  # confira o PID real
$ kill -9 <pid>          # SIGKILL direto
$ squire unlock          # limpa o lock
```

### "Editei `tasks.json` durante uma sessão ativa — meu edit sumiu"

Provável: o squire fez `save_tasks` depois da sua edição, sobrescrevendo.
Workflow seguro:

```bash
$ squire kill       # ou Ctrl+C na sessão
$ nano $SQUIRE_STATE_ROOT/projects/my-app/tasks.json
$ squire resume my-app
```

## Próximas leituras

- [CLI: comandos de controle](cli.md#controle) — `kill`, `unlock`
- [CLI: comandos de recuperação](cli.md#recuperação) — `unblock`, `reset`
- [Tasks](tasks.md) — schema do `tasks.json`
- [Custos e orçamento](custos-e-orcamento.md) — recuperação de cap USD excedido
