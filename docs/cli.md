# CLI

🇧🇷 Português · [🇬🇧 English](en/cli.md)

Referência completa de todos os subcomandos do `squire`. O dispatcher fica
no script bash `squire` (raiz do repo); cada subcomando é uma função
`cmd_<nome>` lá. Para tasks, ele delega para `tasks_cli.py`.

> **Tip:** rode `squire help` ou `squire <comando> --help` para ver o resumo
> no terminal. Esta página é mais detalhada com exemplos e output esperado.

## Sumário

- [Execução](#execução): `run` · `bg` · `resume` · `dry`
- [Observação](#observação): `status` · `log` · `doctor`
- [Controle](#controle): `kill` · `unlock`
- [Recuperação](#recuperação): `unblock` · `reset` · `fix`
- [Alertas](#alertas): `alerts list|ack|rm`
- [Tasks](#tasks): `tasks list|add|edit|rm|split|plan`
- [Projeto](#projeto): `new` · `projects` · `rm`
- [Orçamento](#orçamento): `budget` · `budget set` · `budget reset`
- [Agente](#agente): `agent`
- [Ajuda](#ajuda): `help`

## Execução

### `squire run <projeto>`

Executa o ciclo principal em foreground. Adquire o session lock, lê o
checkpoint, e processa todas as tasks pendentes em ordem.

| Flag       | Descrição                                                |
| ---------- | -------------------------------------------------------- |
| `--quiet`  | Suprime o preview das instruções/respostas (`┊` markers) |
| `--dry-run`| Simula sem chamar backends (atalho: `squire dry`)        |
| `--resume` | Retoma do checkpoint (atalho: `squire resume`)           |

**Exemplo:**

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

**Veja também:** [`squire bg`](#squire-bg-projeto), [`squire resume`](#squire-resume-projeto-bg), [Tasks](tasks.md).

### `squire bg <projeto>`

Igual a `run` mas em background via `nohup`, com stdout redirecionado para
`/tmp/squire.log`. Acompanhe com `squire log`.

```bash
$ squire bg squire-dashboard
→ Iniciando 'squire-dashboard' em background → /tmp/squire.log
✓ Rodando com PID 28471
  Acompanhe com: squire log
```

### `squire resume <projeto> [bg]`

Retoma uma sessão interrompida do checkpoint. Adicione `bg` para retomar
em background.

```bash
$ squire resume squire-dashboard
→ Retomando 'squire-dashboard' do checkpoint...
[14:35:12] → session_resumed
[14:35:12] → Cursor: task-003, step=homologation, attempt 2/5
```

> **Remark:** se a sessão crashou no meio de uma chamada Claude, o checkpoint
> reposiciona antes do gate mecânico. Você não paga pela call que falhou —
> o `RateLimiter.refund` lida com isso quando aplicável. Veja
> [Custos e orçamento](custos-e-orcamento.md#refund-em-erro).

### `squire dry <projeto>`

Atalho para `squire run --dry-run`. Mostra o que faria sem invocar nenhum
backend nem gastar budget. Útil para inspecionar o cursor antes de retomar.

## Observação

### `squire status [<projeto>]`

Resumo do estado em três blocos:

1. **Sessão ativa** — lock holder, PID, ou "Nenhuma sessão ativa"
2. **Projetos** — para cada projeto, status + contagem `done/total` de tasks
3. **Rate limit** — calls na janela atual + tempo até reset
4. **Budget** — gasto hoje + cap configurado + warning a ≥75%

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

`tail -f /tmp/squire.log` — útil quando rodando em background. Bloqueia
até Ctrl+C.

```bash
$ squire log
[14:42:08] → Rodada 2/5 — inner loop: [task-004] Add CommitLog component
[14:42:08] →   ┊→ ## Task: Add CommitLog component
...
```

### `squire doctor [--fix]`

Health check do ambiente (delegado para `doctor.py`). Verifica tudo que
precisa estar de pé para uma sessão rodar e imprime `[ OK ]/[WARN]/[FAIL]/[INFO]`
por item. Sai com código 1 se houver qualquer FAIL.

Checks: state root gravável · endpoint do LLM acessível + modelos
configurados disponíveis · binário `claude` no PATH (+versão) · binários
dos backends em uso (`opencode`/`crush`) · `session.lock` (pid vivo? TTL
expirado?) · `llm.lock` (flock em uso?) · sanidade por projeto (git repo,
working tree sujo, tasks bloqueadas, sessão morta retomável) · alertas
pendentes · frescor do `global-stats.json`.

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

`--fix` aplica apenas limpezas seguras: remove `session.lock` cujo pid
está comprovadamente morto e o arquivo `llm.lock` quando o flock está
livre. Nunca remove locks de processos vivos.

## Controle

### `squire kill`

Mata o processo da sessão ativa (SIGTERM, depois SIGKILL após 1s) e remove
o lock. Use quando a sessão travou e não responde a Ctrl+C.

```bash
$ squire kill
⚠ Encerrando PID 28471...
✓ Processo encerrado.
✓ Lock removido.
```

> [!WARNING]
> `kill` é brutal. Para parar graciosamente, use Ctrl+C no terminal onde
> o `squire run` está rodando — o squire libera o lock corretamente e
> grava `recovery.resume_action = "continue"` no checkpoint, deixando
> tudo pronto para `squire resume`.

### `squire unlock`

Remove o `session.lock` residual deixado por um crash (sem matar processo).
Use quando `squire status` mostra "Lock residual encontrado (processo morto)".

```bash
$ squire unlock
✓ Lock removido.
```

## Recuperação

### `squire unblock <projeto> [task-id …]`

Marca tasks com status `blocked` (atingiram `max_homologation_attempts`)
de volta para `pending`. Mantém o código que já foi escrito no repositório.
Sem `task-id`, desbloqueia todas as bloqueadas. Limpa `rejection_summaries`
e `no_progress_streak` para evitar disparo imediato da detecção de loops.

```bash
$ squire unblock squire-dashboard task-005
  ✓ task-005 → pending  (Add commit log empty state)

1 task(s) desbloqueada(s).
```

**Veja também:** [`squire reset`](#squire-reset-projeto-task-id) (mais agressivo, descarta código).

### `squire reset <projeto> [task-id …]`

Reseta tasks para `pending` **e** descarta o trabalho com `git reset HEAD`
+ `git checkout -- .` no `repo_path`. Sem `task-id`, reseta todas as tasks
do projeto. Também limpa o cursor do checkpoint.

```bash
$ squire reset squire-dashboard task-005
  ✓ task-005 → pending  (Add commit log empty state)

1 task(s) resetada(s).
  ✓ checkpoint cursor resetado
⚠ Limpando git state em /home/ai-debian/squire-dashboard
✓ git checkout -- . OK
```

> [!WARNING]
> `reset` descarta alterações não commitadas no working tree do projeto.
> O squire faz auto-commit após cada task aprovada, então geralmente só
> a task corrente é perdida — mas confirme com `git status` no repo antes.

### `squire fix <projeto> <task-id>`

Ciclo completo de correção para uma task **bloqueada** (delegado para
`fix_cli.py`): o Claude Code implementa a correção diretamente — usando os
vereditos completos do `homologation_log.json` como contexto (fallback:
`rejection_summaries`) e com proibição explícita de tocar em arquivos de
teste — os testes do projeto rodam, e **uma** rodada de homologação decide:

- **Aprovada** → task vira `completed` (`claude_code_assisted=true`),
  commit `fix: [task-id] título`, e o status do projeto é recalculado
  (sem bloqueios restantes → sai de `blocked`).
- **Rejeitada** → permanece `blocked`, com o veredito novo gravado no log
  (`source: "fix"`) para triagem humana.

Segura o session lock durante o ciclo (recusa rodar com sessão ativa).
Custo típico: 2-3 chamadas Claude (~$0.10–0.30); tudo contabilizado no
`global-stats.json`. É o que o botão **"Corrigir com Claude"** do
dashboard executa, via fila do agente (`fix_task`).

| Exit code | Significado                                  |
| --------- | -------------------------------------------- |
| 0         | Aprovada e concluída                         |
| 1         | Projeto/task não encontrado                  |
| 2         | Task não está `blocked`                      |
| 3         | Session lock ativo                           |
| 4         | Claude não escreveu arquivos                 |
| 5         | Erro de infra na homologação (task intocada) |
| 6         | Correção rejeitada (permanece blocked)       |

## Alertas

Subcomandos delegados para `alerts_cli.py`. Alertas são gerados pelo squire
em casos como `max_homologations_reached` e budget excedido, e ficam em
`$SQUIRE_STATE_ROOT/alerts.json` até serem reconhecidos ou removidos.

### `squire alerts list [--all] [--project <id>]`

Lista alertas pendentes (não-reconhecidos) com índice 1-based, severidade,
projeto/task, idade e mensagem. `--all` inclui os já reconhecidos (sem
índice); `--project` filtra por projeto.

```bash
$ squire alerts list
Alertas pendentes (2):
  1  CRIT  claw-code-study/task-026a  71d  max_homologations_reached: Task '...' falhou 5 homologações
  2  CRIT  semanario-infantil/task-009  65d  max_homologations_reached: Task '...' falhou 5 homologações
```

`squire alerts` sem subcomando é alias de `list`.

### `squire alerts ack <n> [<n>…] | --all [--project <id>] [--task <id>]`

Marca alertas como reconhecidos (`acknowledged: true` — o mesmo campo que
o dashboard escreve). Por índice (referente à listagem de pendentes) ou em
lote com `--all`, opcionalmente filtrado por `--project`/`--task`.

```bash
$ squire alerts ack 1 2
✓ 2 alerta(s) reconhecido(s).

$ squire alerts ack --all --project semanario-infantil
✓ 4 alerta(s) reconhecido(s).
```

> [!NOTE]
> O dashboard é um segundo escritor de `alerts.json` (POST `/api/alerts/ack`).
> Índices podem sofrer corrida se um alerta for dispensado pelo dashboard
> entre o `list` e o `ack` — em ambientes com dashboard ativo, prefira os
> seletores `--project`/`--task`.

### `squire alerts rm <n> [<n>…] | --acked | --all`

Remove alertas do arquivo (equivalente ao "dismiss" do dashboard).
`--acked` remove só os já reconhecidos; `--all` limpa tudo.

```bash
$ squire alerts rm --acked
✓ 13 alerta(s) removido(s).
```

## Tasks

Subcomandos delegados para `tasks_cli.py`. Para detalhe do modelo Task e da
forma do `tasks.json`, veja [Tasks](tasks.md).

### `squire tasks list <projeto>`

Lista tasks com status visual. Atalho: `squire tasks <projeto>` (sem subcomando).

```bash
$ squire tasks squire-dashboard
  ✓ [task-001] Setup Next.js scaffolding
  ✓ [task-002] Add fixture data loaders
  ⟳ [task-003] Implement ProjectCard component
  · [task-004] Implement Timeline component
  · [task-005] Implement AlertBanner component
  ...
```

Legenda: `✓` completed · `⟳` implementing · `⌛` homologating · `·` pending · `✗` blocked.

### `squire tasks add <projeto>`

Adiciona uma task interativamente ou via flags.

| Flag                    | Descrição                                                  |
| ----------------------- | ---------------------------------------------------------- |
| `--title "..."`         | Título obrigatório                                         |
| `--desc "..."`          | Descrição (do contrário, abre `$EDITOR`)                   |
| `--id "..."`            | ID custom (default: próximo `task-NNN` livre)              |
| `--skip-homolog`        | Auto-aprovação após inner loop (sem chamar Claude)         |
| `--max N`               | `max_attempts` (default: 10)                                |
| `--max-homolog N`       | `max_homologation_attempts` (default: 5)                    |
| `--no-ask`              | Pula o prompt de campos avançados (effort/tdd/test_author)  |
| `--spec` / `--no-spec`  | Atualiza/pula o SPEC.md sem perguntar                       |

### `squire tasks edit <projeto> [task-id]`

Abre a task no `$EDITOR` (formato YAML editável). Sem `task-id`, abre o
arquivo `tasks.json` inteiro.

### `squire tasks rm <projeto> <task-id> [--yes]`

Remove a task após confirmação simples. `--yes` pula a confirmação
(scripts e o agente host usam isso).

### `squire tasks split <projeto> <task-id> [--yes]`

Pede ao Claude para subdividir a task em subtasks/subitems. Mostra a
proposta e permite refinar uma vez antes de aplicar. `--yes` aceita a
primeira proposta sem confirmação.

### `squire tasks plan <projeto> [--desc "..."] [--mode append|replace] [--no-refine] [--yes] [--spec|--no-spec]`

Pede ao Claude para gerar a lista inicial de tasks a partir de uma
descrição livre. Até 3 ciclos de refinamento interativo. Pergunta no fim
se você quer substituir ou anexar ao `tasks.json` atual — **Enter
significa anexar** (escolha não-destrutiva).

Modo não-interativo (usado pelo agente host / dashboard):

- `--yes` — zero prompts: sem refinamento, modo `append` por padrão,
  SPEC.md pulado a menos que `--spec` seja passado. Recusa rodar se há
  uma sessão squire ativa (não disputa o `tasks.json` com ela).
- `--mode append|replace` — decide anexar/substituir sem perguntar.
- `--no-refine` — só o primeiro rascunho, sem loop de feedback.

```bash
$ squire tasks plan squire-dashboard --desc "Next.js page reading JSON state"
[planning] Claude gerando rascunho...
[planning] 11 tasks propostas. Refinar? [y/N] n
[planning] Modo: (s)ubstituir / (a)nexar / (c)ancelar? s
✓ 11 tasks gravadas em tasks.json
```

## Projeto

### `squire new <projeto>`

Cria um novo projeto com `project.json` + `tasks.json` template no
`STATE_ROOT/projects/<projeto>/`.

| Flag                  | Default                                       |
| --------------------- | --------------------------------------------- |
| `--repo <path>`       | `/home/ai-debian/projects/<projeto>`          |
| `--name <nome>`       | `<projeto>` (mesmo do ID)                     |
| `--stack <csv>`       | `typescript`                                  |
| `--backend <name>`    | `opencode` (também aceita `litellm`, `crush`) |
| `--yes`               | Pula o prompt "planejar tasks com Claude?"    |
| `--git-init`          | Cria o repo com `git init` + commit vazio     |

```bash
$ squire new my-api --repo /home/ai-debian/projects/my-api \
              --stack python,fastapi --backend opencode
✓ Projeto 'my-api' criado em /home/ai-debian/squire-state/projects/my-api

  Deseja planejar as tasks agora com Claude? [y/N] n

  Próximos passos:
  1. Edite as tasks:   nano /home/ai-debian/squire-state/projects/my-api/tasks.json
  2. Crie o repo:      mkdir -p /home/ai-debian/projects/my-api && cd ... && git init
  3. Execute:          squire run my-api
```

### `squire projects`

Lista os projetos disponíveis (basename dos diretórios em `STATE_ROOT/projects/`).

```bash
$ squire projects
Projetos disponíveis:
  squire-dashboard
  pilotinho
  my-api
```

### `squire rm <projeto>`

Remove o estado do projeto após **confirmação dupla**: você precisa digitar
`<projeto> <palavra-NATO>` (por exemplo `my-api echo`) para confirmar.
O `repo_path` (código no disco) NÃO é tocado.

```bash
$ squire rm my-api
⚠  Remoção de projeto: my-api
   Diretório de estado: /home/ai-debian/squire-state/projects/my-api
   Arquivos: project.json, tasks.json, checkpoint.json, history.json
   Repositório de código (não será removido): /home/ai-debian/projects/my-api

Para confirmar, digite exatamente: my-api echo
(Ctrl+C para cancelar)

> my-api echo
✓ Projeto 'my-api' removido.
```

> **Insight:** o uso de palavra do alfabeto NATO (alpha, bravo, charlie, ...
> zulu) evita `rm` acidental por copy-paste do histórico — você precisa ler
> o prompt para saber qual palavra digitar. Veja [`squire.py:1275`](../squire.py).

## Orçamento

Comandos relacionados ao rastreamento de custo e aos caps USD. Detalhes em
[Custos e orçamento](custos-e-orcamento.md).

### `squire budget` (ou `squire budget show`)

Mostra gasto hoje + cap configurado + breakdown por modelo.

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
  (ou exporte SQUIRE_DAILY_USD_BUDGET / SQUIRE_PER_TASK_USD_CAP)
```

### `squire budget set --daily X --per-task Y`

Persiste caps USD em `$SQUIRE_STATE_ROOT/budget.json`. Env vars
(`SQUIRE_DAILY_USD_BUDGET`, `SQUIRE_PER_TASK_USD_CAP`) têm prioridade
sobre o arquivo.

```bash
$ squire budget set --daily 15 --per-task 3
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json
  daily_usd:    $15.00
  per_task_usd: $3.00
```

### `squire budget reset`

Zera os contadores diários (`global-stats.json`). Útil quando você quer
recomeçar a contagem sem esperar a virada UTC.

```bash
$ squire budget reset
✓ Contadores diários resetados para 2026-05-11
```

## Agente

### `squire agent [--once] [--poll N]`

Executa comandos enfileirados pelo dashboard (delegado para `agent_cli.py`).
O dashboard roda em container sem acesso aos repos nem aos binários do
host — qualquer operação que precise deles (criar projeto, run/resume/kill,
planejar tasks com Claude) vira um arquivo em
`$SQUIRE_STATE_ROOT/commands/pending/<uuid>.json`, que o agente reivindica
(rename atômico para `running/`), executa e responde em `done/<uuid>.json`.

- Whitelist estrita: `new_project`, `run`, `resume`, `kill`, `plan_tasks`,
  `split_task`, `fix_task` — com validação de `project_id`/args e argv em
  lista (nunca shell).
- `--once` processa a fila e sai (útil em testes/cron); sem flag, loop
  contínuo com poll de 2s.
- Instância única via pidfile (`commands/agent.pid`).
- Comandos órfãos (agente reiniciado no meio) viram `failed` — nunca são
  re-executados.
- Resultados em `done/` expiram após `SQUIRE_COMMAND_TTL_H` (default 24h).

Para rodar como serviço (sobrevive a logout/reboot):

```ini
# ~/.config/systemd/user/squire-agent.service
[Unit]
Description=Squire command agent

[Service]
ExecStart=/home/ai-debian/squire/squire agent
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
$ loginctl enable-linger ai-debian          # systemd --user sem sessão ativa
$ systemctl --user daemon-reload
$ systemctl --user enable --now squire-agent
```

## Ajuda

### `squire help`

Imprime o resumo de todos os comandos. Aliases: `squire -h`, `squire --help`,
e `squire` (sem argumentos).

## Apêndice — variáveis de ambiente da CLI

| Variável            | Default                          | Descrição                                              |
| ------------------- | -------------------------------- | ------------------------------------------------------ |
| `SQUIRE_STATE_ROOT` | `/home/ai-debian/squire-state`   | Raiz do estado persistente (todos os comandos a usam)  |
| `EDITOR`            | `nano`                           | Editor para `squire tasks edit`                        |

Outras env vars (que afetam o comportamento do orquestrador, não a CLI em si)
estão em [Configuração](configuracao.md).
