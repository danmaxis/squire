# Configuração

🇧🇷 Português · [🇬🇧 English](en/configuration.md)

Todas as variáveis de ambiente, arquivos de configuração e knobs do squire.
Todos os valores têm defaults sensatos; você só precisa setar o que quer
mudar.

## Sumário

- [Precedência](#precedência)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Arquivos de configuração](#arquivos-de-configuração)
- [Caminhos e diretórios](#caminhos-e-diretórios)
- [Tabela de preços](#tabela-de-preços)

## Precedência

A ordem de precedência (do mais forte para o mais fraco) é:

1. **Argumento de linha de comando** (ex: `squire run --quiet`)
2. **Variável de ambiente** (ex: `SQUIRE_DAILY_USD_BUDGET=15`)
3. **Arquivo de configuração** (ex: `budget.json`)
4. **Default hardcoded** (em `config.py`)

> **Insight — por que env vars > arquivos?**
> Princípio 12-factor: env vars são portáteis entre dev/staging/prod sem
> editar arquivos no repo. O arquivo é fallback conveniente para valores que
> mudam pouco (caps de budget) ou são pessoais (paths).

## Variáveis de ambiente

Todas começam com `SQUIRE_`. Source: [`config.py`](../config.py).

### Paths

| Variável             | Default                          | Efeito                                         |
| -------------------- | -------------------------------- | ---------------------------------------------- |
| `SQUIRE_STATE_ROOT`  | `/home/ai-debian/squire-state`   | Raiz do estado persistente (todos os JSONs)    |

> [!IMPORTANT]
> Nenhuma variável é obrigatória: `SQUIRE_STATE_ROOT` tem default
> `/home/ai-debian/squire-state` (o mesmo que o wrapper bash `squire` usa).
> Sete a env var para apontar o estado para outro lugar — a suíte de testes
> faz isso (em `tests/conftest.py`) para nunca tocar o estado real.

### LLM local (endpoint OpenAI-compatible)

Qualquer endpoint OpenAI-compatible serve: LiteLLM gateway, **Ollama**
(`/v1`), llama.cpp server. No setup atual, é o Ollama no Zordon
(`http://192.168.50.24:11434/v1`) servindo `journal-synth:latest`.

| Variável                | Default                              | Efeito                                          |
| ----------------------- | ------------------------------------ | ----------------------------------------------- |
| `SQUIRE_LITELLM_URL`    | `http://localhost:4000/v1`           | Base URL do endpoint OpenAI-compatible          |
| `SQUIRE_LITELLM_MODEL`  | `journal-synth`                      | Modelo default (id/alias no endpoint)           |
| `SQUIRE_LITELLM_KEY`    | `sk-local`                           | API key (placeholder — endpoints locais não exigem) |
| `SQUIRE_MODEL_LOW`      | igual a `LITELLM_MODEL`              | Modelo para tasks com `effort=low`              |
| `SQUIRE_MODEL_MEDIUM`   | igual a `LITELLM_MODEL`              | Modelo para tasks com `effort=medium`           |
| `SQUIRE_MODEL_HIGH`     | igual a `LITELLM_MODEL`              | Modelo para tasks com `effort=high`             |

### Inner loop

| Variável                    | Default | Efeito                                                    |
| --------------------------- | ------- | --------------------------------------------------------- |
| `SQUIRE_INNER_MAX_ATTEMPTS` | `10`    | Tentativas por rodada (override por-task em `tasks.json`) |
| `SQUIRE_INNER_TIMEOUT`      | `1200`  | Timeout (s) de uma chamada ao backend                     |

### Backends

| Variável                  | Default     | Efeito                                                                  |
| ------------------------- | ----------- | ----------------------------------------------------------------------- |
| `SQUIRE_CODING_BACKEND`   | `opencode`  | Backend default (override em `project.json` via `coding_backend`)        |
| `SQUIRE_OPENCODE_BIN`     | `opencode`  | Caminho/nome do binário do opencode (busca no `$PATH` se relativo)      |
| `SQUIRE_CRUSH_BIN`        | `crush`     | Caminho/nome do binário do crush                                        |
| `SQUIRE_AIDER_BIN`        | `aider`     | **Deprecated.** Aider foi descontinuado, esta var não tem mais efeito.  |

### Claude Code

| Variável                  | Default   | Efeito                                                  |
| ------------------------- | --------- | ------------------------------------------------------- |
| `SQUIRE_CLAUDE_BIN`       | `claude`  | Binário do Claude Code CLI                              |
| `SQUIRE_CC_MAX_CALLS`     | `10`      | Calls máximas por janela (rate limit secundário)        |
| `SQUIRE_CC_WINDOW_MIN`    | `30`      | Duração da janela em minutos                            |

### Homologação

| Variável                | Default | Efeito                                                          |
| ----------------------- | ------- | --------------------------------------------------------------- |
| `SQUIRE_MAX_HOMOLOG`    | `5`     | Rodadas máximas por task (default — override em `tasks.json`)   |
| `SQUIRE_LOOP_DETECT`    | `3`     | Rejeições consecutivas com mesmo padrão → escalação forçada     |
| `SQUIRE_NO_PROGRESS`    | `3`     | Ciclos sem arquivo modificado → escalação forçada               |

### Fila de comandos / agente

| Variável                  | Default                       | Efeito                                                       |
| ------------------------- | ----------------------------- | ------------------------------------------------------------ |
| `SQUIRE_COMMAND_TTL_H`    | `24`                          | Horas até resultados em `commands/done/` serem apagados      |
| `SQUIRE_COMMAND_TIMEOUT`  | `900`                         | Timeout (s) de execução de um comando enfileirado            |
| `SQUIRE_AGENT_POLL`       | `2`                           | Intervalo (s) de polling do `squire agent`                   |
| `SQUIRE_AGENT_REPO_ROOT`  | `/home/ai-debian/projects`    | Raiz permitida para `repo_path` de projetos criados via fila |

### Sessão e lock

| Variável                | Default | Efeito                                                            |
| ----------------------- | ------- | ----------------------------------------------------------------- |
| `SQUIRE_LOCK_TTL`       | `60`    | TTL do session lock (minutos). Heartbeat renova durante operação. |
| `SQUIRE_HEARTBEAT`      | `300`   | Intervalo (s) entre heartbeats (renova lock + grava checkpoint)   |

### Budget / custo

| Variável                       | Default | Efeito                                                              |
| ------------------------------ | ------- | ------------------------------------------------------------------- |
| `SQUIRE_DAILY_USD_BUDGET`      | `0`     | Cap USD diário global (0 = sem limite)                              |
| `SQUIRE_PER_TASK_USD_CAP`      | `0`     | Cap USD default por task (`Task.max_usd` sobrescreve)               |
| `SQUIRE_ESTIMATED_CALL_USD`    | `0.05`  | Custo estimado de uma call antes de saber o real (usado em `can_afford`) |

Veja [Custos e orçamento](custos-e-orcamento.md) para o sistema completo.

## Arquivos de configuração

### `$SQUIRE_STATE_ROOT/budget.json`

Persistido por `squire budget set`. Env vars têm precedência.

```json
{
  "daily_usd": 10.0,
  "per_task_usd": 2.0
}
```

### `$SQUIRE_STATE_ROOT/projects/<id>/project.json`

Metadata do projeto. Schema: [`models.Project`](../models.py).

```json
{
  "id": "squire-dashboard",
  "name": "Squire Dashboard",
  "description": "Painel Next.js mostrando o estado dos projetos do squire",
  "repo_path": "/home/ai-debian/squire-dashboard",
  "stack": ["typescript", "nextjs", "tailwind"],
  "status": "implementing",
  "created_at": "2026-03-24T18:32:00Z",
  "updated_at": "2026-05-11T14:24:33Z",
  "current_task_id": "task-004",
  "coding_backend": "opencode"
}
```

- `coding_backend` — sobrescreve `SQUIRE_CODING_BACKEND` para este projeto.
  Valores válidos: `"litellm"`, `"opencode"`, `"crush"`.
- `repo_path` — caminho absoluto para o repositório de código. Auto-snapshot
  e auto-commit do squire operam aqui.
- `stack` — informativo (não afeta comportamento ainda; futuro: hint para o
  gate mecânico).
- `current_task_id` — atualizado pelo squire conforme o cursor avança.

### `$SQUIRE_STATE_ROOT/projects/<id>/tasks.json`

Backlog. Schema completo em [Tasks](tasks.md).

### `$SQUIRE_STATE_ROOT/projects/<id>/checkpoint.json`

Persistido a cada transição de estado. Não edite manualmente — use
`squire reset` ou `squire unblock` para mexer no cursor. Schema:
[`models.Checkpoint`](../models.py).

### `$SQUIRE_STATE_ROOT/global-stats.json`

Contadores agregados do dia. Auto-resetado quando o dia UTC vira.

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

`approval_first_try_rate` é o percentual (0–100) de tasks aprovadas na
1ª homologação dentre as homologadas hoje (`tasks_approved_first_try_today
/ tasks_homologated_today`). Tasks com `skip_homologation` contam em
`tasks_completed_today` mas ficam de fora da taxa — são auto-aprovadas e
inflariam o número.

Reset com `squire budget reset`.

### `$SQUIRE_STATE_ROOT/alerts.json`

Lista de alertas (warnings / criticals) que requerem atenção humana.
Auto-populado pelo squire em casos como: task atingiu `max_homologation_attempts`,
budget per-task excedido, lock corrompido.

### `.env.example` (na raiz do repo)

Template de env vars para você copiar para `.env`. O wrapper bash `squire`
faz `source .env` automaticamente na inicialização; use exports guardados
(`export VAR="${VAR:-valor}"`) para que variáveis já exportadas no shell
tenham precedência sobre o arquivo:

```bash
# Obrigatório
SQUIRE_STATE_ROOT=/home/ai-debian/squire-state

# Opcionais (defaults mostrados)
# SQUIRE_LITELLM_URL=http://localhost:4000/v1
# SQUIRE_LITELLM_MODEL=journal-synth
# SQUIRE_CODING_BACKEND=opencode

# Budget (recomendado em produção)
# SQUIRE_DAILY_USD_BUDGET=10.0
# SQUIRE_PER_TASK_USD_CAP=2.0
```

## Caminhos e diretórios

Layout completo do `$SQUIRE_STATE_ROOT/`:

```text
$SQUIRE_STATE_ROOT/
├── session.lock                  ← lock global
├── budget.json                   ← caps USD persistidos
├── global-stats.json             ← contadores diários
├── alerts.json                   ← alertas ativos
├── rate.json                     ← rate state (legado, atualmente não usado)
└── projects/
    └── <project-id>/
        ├── project.json
        ├── tasks.json
        ├── checkpoint.json
        ├── history.json
        └── progress.txt          ← memória de longo prazo
```

Em produção (no Unraid), o `STATE_ROOT` típico é `/mnt/user/data/squire/`
(volume montado). Em dev, qualquer diretório com permissão de escrita serve.

## Tabela de preços

A tabela `MODEL_PRICING_PER_1M` em [`config.py:111`](../config.py) mapeia
nomes de modelo para `(USD/1M input tokens, USD/1M output tokens)`. Valores
default refletem a tabela pública da Anthropic em 2026-Q1:

| Modelo                | Input ($/1M)  | Output ($/1M) |
| --------------------- | ------------- | ------------- |
| `claude-opus-4-7`     | 15.00         | 75.00         |
| `claude-opus-4-6`     | 15.00         | 75.00         |
| `claude-sonnet-4-6`   | 3.00          | 15.00         |
| `claude-sonnet-4-5`   | 3.00          | 15.00         |
| `claude-haiku-4-5`    | 1.00          | 5.00          |
| `journal-synth`       | 0.00          | 0.00          |

**Para estender:** edite o dict em `config.py` diretamente. Não há env var
por modelo (UX ruim com 20+ vars). O matching é exato com fallback para
prefix match — ex: `claude-opus-4-7[1m]` casa com `claude-opus-4-7` pela
regra de prefixo.

Modelos desconhecidos custam `(0, 0)` — o squire ainda registra tokens
mas trata como gratuito. Se o Claude Code reportar `total_cost_usd` no JSON,
esse valor tem precedência sobre o cálculo da tabela
([`homologator.py:_extract_usage_from_claude_json`](../homologator.py)).

## Próximas leituras

- [Custos e orçamento](custos-e-orcamento.md) — como o cap USD diário/por-task funciona
- [Estado e recuperação](estado-e-recuperacao.md) — formato e propósito de cada JSON
- [CLI](cli.md) — comandos que leem/escrevem essas configurações
