# Custos e orçamento

🇧🇷 Português · [🇬🇧 English](en/cost-and-budget.md)

O squire rastreia o custo USD de cada chamada (Claude e LiteLLM quando o
backend reporta uso) e aplica dois caps: um **orçamento USD diário global**
e um **cap USD por task**. Este documento explica como o rastreamento
funciona, como configurar caps, e o que acontece quando algum estoura.

## Sumário

- [O que é rastreado](#o-que-é-rastreado)
- [Tabela de preços](#tabela-de-preços)
- [Budget USD diário](#budget-usd-diário)
- [Cap por task](#cap-por-task)
- [Comportamento ao estourar](#comportamento-ao-estourar)
- [Refund em erro](#refund-em-erro)
- [Tokens unknown](#tokens-unknown)
- [Comandos CLI](#comandos-cli)
- [Insights e remarks](#insights-e-remarks)

## O que é rastreado

Para cada chamada (Claude Code ou backend local), o squire grava:

- **`prompt_tokens`** e **`completion_tokens`** — quando o backend expõe
- **`cached_tokens`** — quando aplicável (Claude prompt caching)
- **`cost_usd`** — calculado via tabela de preços OU lido direto do envelope
  do Claude (`total_cost_usd`)
- **`model`** — string do modelo usado
- **`tokens_unknown`** — flag `true` quando o backend não reportou uso
  (ex: opencode/crush CLI)

Esses campos vivem no struct `TokenUsage` ([`models.py:345`](../models.py)).

A contabilidade é centralizada em `Squire._account_call`
([`squire.py:104`](../squire.py)) que:

1. Soma `cost_usd` em `GlobalStats.cost_estimate_usd` (acumulado do dia)
2. Soma `tokens` em `GlobalStats.daily_tokens`
3. Acumula em `GlobalStats.cost_by_model[modelo]`
4. Acumula em `Task.cost_usd` (custo desta task específica)
5. Incrementa `GlobalStats.daily_calls_unknown_cost` quando `tokens_unknown`

E `RateLimiter.record_call(cost_usd=…)` ([`rate_limiter.py`](../rate_limiter.py))
atualiza `state.daily_cost_usd` no checkpoint para que o budget gate
funcione.

## Tabela de preços

Em `MODEL_PRICING_PER_1M` ([`config.py:111`](../config.py)):

| Modelo               | Input ($/1M)  | Output ($/1M) |
| -------------------- | ------------- | ------------- |
| `claude-opus-4-7`    | 15.00         | 75.00         |
| `claude-opus-4-6`    | 15.00         | 75.00         |
| `claude-sonnet-4-6`  | 3.00          | 15.00         |
| `claude-sonnet-4-5`  | 3.00          | 15.00         |
| `claude-haiku-4-5`   | 1.00          | 5.00          |
| `journal-synth`      | 0.00          | 0.00          |

`config.compute_cost_usd(prompt_tokens, completion_tokens, model)` faz a
matemática. Modelos desconhecidos retornam `(0, 0)` — o squire ainda
registra tokens mas trata como gratuito.

Para o Claude Code (invocado via `claude --print --output-format json`),
o envelope do response inclui `total_cost_usd` diretamente — esse valor
tem precedência sobre o cálculo da tabela, então mesmo que a tabela
desatualize, o número permanece correto.

> **Insight — fallback de cálculo.**
> Se o Claude omitir `total_cost_usd` mas reportar tokens + model,
> `_extract_usage_from_claude_json` ([`homologator.py:25`](../homologator.py))
> recompõe o custo via tabela. Defense in depth.

## Budget USD diário

Cap USD global de gasto por dia (UTC). Quando excede, o squire pausa até
`midnight UTC`.

### Configurar

Três caminhos, em ordem de precedência:

1. **Env var:** `SQUIRE_DAILY_USD_BUDGET=10`
2. **CLI:** `squire budget set --daily 10`
3. **Default:** `0` (sem limite)

A opção 2 persiste em `$SQUIRE_STATE_ROOT/budget.json`. A opção 1 vence
sobre a 2 se ambos estiverem setados.

```bash
$ squire budget set --daily 10 --per-task 2
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json
  daily_usd:    $10.00
  per_task_usd: $2.00
```

### Como o gate funciona

Antes de cada chamada Claude, o squire chama `rate_limiter.can_afford(estimated_cost)`
([`rate_limiter.py:can_afford`](../rate_limiter.py)). O estimated_cost
default é `SQUIRE_ESTIMATED_CALL_USD` (`$0.05`). Se a chamada projetada
estouraria o budget, retorna `False` e o squire pausa.

O gate é duplo:

```python
def can_afford(self, estimated_cost_usd: float = 0.0) -> bool:
    # 1. Call-count (secundário): pega loops infinitos
    if self.claude_code_calls_this_window >= max_calls_per_window:
        return False
    # 2. Budget USD diário (primário): só aplica se max_daily_usd > 0
    if self.max_daily_usd > 0:
        if (daily_cost_usd + estimated_cost_usd) > max_daily_usd:
            return False
    return True
```

> **Insight — por que call-count E USD budget?**
> *Defense in depth*. Cap USD não pega o caso de centenas de chamadas
> baratas em loop (um bug que itera sem produzir trabalho útil). Call-count
> não pega o caso de uma chamada cara que estoura o orçamento sozinha.
> Os dois juntos cobrem ambos.

### Warnings de threshold

Quando o gasto cruza 75% do cap, `RateLimiter._maybe_warn_budget_threshold`
([`rate_limiter.py`](../rate_limiter.py)) imprime:

```
[budget] ⚠ 75% do budget diário usado ($7.50/$10.00)
```

Quando atinge 100%:

```
[budget] ✗ Budget diário esgotado ($10.05/$10.00) — pausando até midnight UTC
```

Cada warning dispara uma única vez por dia (flag transiente). O reset
acontece automaticamente quando o dia UTC vira.

## Cap por task

`Task.max_usd` define um cap USD individual. Se `null` ou `0`, usa
`PER_TASK_USD_CAP` (env var global, default `0` = sem limite).

```json
{
  "id": "task-007",
  "title": "Refator complexo do auth middleware",
  "max_usd": 1.50
}
```

Verificação acontece dentro do inner loop ([`squire.py`](../squire.py)
`_run_inner_loop`):

```python
if self._task_budget_exceeded(task):
    cap = task.max_usd or config.PER_TASK_USD_CAP
    log(f"Task budget esgotado (${task.cost_usd:.2f} >= ${cap:.2f}) — pausando", "warn")
    ckpt.add_alert(..., severity=AlertSeverity.warning)
    return False
```

Mesma verificação acontece no topo de cada rodada de homologação, então
mesmo que o cap seja excedido entre rodadas, a task aborta antes de gastar
mais.

## Comportamento ao estourar

### Budget diário esgotado

O squire **pausa** (não falha). O comportamento depende do contexto:

- **Antes de uma call Claude:** `can_afford(0.05)` retorna `False`, squire
  loga warning, e para a task corrente. Em `_run_homologation`, chama
  `_wait_productively` que continua o inner loop com o feedback acumulado
  enquanto aguarda.
- **Entre tasks:** próxima task pendente é tentada na próxima vez que o
  budget tiver folga.
- **Reset automático:** quando o relógio passa de midnight UTC, o contador
  é zerado em `_maybe_reset_daily_budget`.

### Cap por task excedido

A task é marcada como `blocked`, um Alert (severity warning) é gerado em
`alerts.json`, e o squire avança para a próxima task pendente. Para
desbloquear:

```bash
# Aumentar o cap e desbloquear:
$ squire tasks edit my-app task-007  # edita max_usd no JSON
$ squire unblock my-app task-007     # blocked → pending
```

## Refund em erro

`RateLimiter.refund(cost_usd)` desconta um custo já registrado. Útil
quando uma call Claude retorna erro antes de produzir output útil — você
não deveria pagar por uma falha de rede.

Estado atual: o squire **não** chama refund automaticamente em todos os
caminhos (apenas o método existe, pronto para ser usado pelos call sites
quando um erro de chamada for distinguível de uma falha de modelo).
Próxima iteração vai fechar isso. Veja o roadmap em
[/home/ai-debian/.claude/plans/](../../.claude/plans/).

```python
# Exemplo de uso (já compatível):
rl.record_call(cost_usd=0.50)   # tentativa de chamada
# ... chamada falha por timeout sem produzir output ...
rl.refund(0.50)                  # estorna
```

## Tokens unknown

OpenCode e Crush (CLIs) não expõem contagem de tokens no stdout de forma
estável. O squire detecta isso e marca `tokens_unknown=True` no `TokenUsage`.
Efeitos:

- `cost_usd = 0` é registrado (não temos como calcular sem tokens)
- `GlobalStats.daily_calls_unknown_cost` é incrementado
- O summary final do `squire run` mostra:

```
⚠ 3 chamada(s) sem usage reportado — custo real pode ser maior
```

> **Remark — não confunda unknown com gratuito.**
> Backend local (LiteLLM/Qwen) custa $0 *de verdade* — você pagou pelo
> hardware uma vez. OpenCode/Crush podem estar chamando APIs pagas por
> baixo (Anthropic, OpenAI, etc.) — só não reportam via stdout. Se você
> roda opencode com `OPENAI_API_KEY` setado, está pagando por chamada,
> mas o squire vai mostrar `$0.000` + um `⚠ tokens_unknown`. Use o
> dashboard do provider para conferir.

## Comandos CLI

### `squire budget` — mostra estado

```bash
$ squire budget
=== Budget — 2026-05-11 (UTC) ===

  Spent hoje:   $7.823  (148,219 tokens)
  Daily cap:    $10.00  (78% usado) ⚠
  Restante:     $2.177
  Per-task cap: $2.00

  Por modelo:
    claude-opus-4-7: $7.823
    journal-synth: $0.000

  ⚠ 3 chamada(s) sem usage reportado — custo real pode ser maior
```

### `squire budget set --daily X --per-task Y`

Persiste em `budget.json`. Veja [seção CLI](cli.md#squire-budget-set---daily-x---per-task-y).

### `squire budget reset`

Zera os contadores diários (`global-stats.json`). Não toca em `budget.json`.

```bash
$ squire budget reset
✓ Contadores diários resetados para 2026-05-11
```

## Sessão completa — exemplo

```bash
# 1. Configurar caps
$ squire budget set --daily 5 --per-task 1
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json

# 2. Rodar (com `max_usd: 1` no tasks.json para uma das tasks)
$ squire run my-app
[14:22:01] → Sessão iniciada: sess-20260511-1422-a3f4c1
[14:22:01] → Projeto: My App (my-app)
[14:22:08] → Inner loop: task-003 (tentativa 1/10)
[14:25:12] → Rodada 1/5 — homologação: task-003
[14:25:30] ✓ Homologação aprovada! (verdict: pequena melhoria sugerida)
[14:25:31] ✓ Task concluída: [task-003] Add timeline ($0.342)
...
[14:31:18] ⚠ 75% do budget diário usado ($3.75/$5.00)
...
[14:34:55] ⚠ Task budget esgotado ($1.02 >= $1.00) — pausando task
[14:34:55] ✗ Task bloqueada: task-007

# 3. Inspecionar
$ squire budget
  Spent hoje:   $4.123  (78,221 tokens)
  Daily cap:    $5.00   (82% usado) ⚠
  Restante:     $0.877
  Per-task cap: $1.00
```

## Insights e remarks

> **Insight — orçamento por dia, não por sessão.**
> O budget é diário (UTC) para que crashes e restarts não te deem
> "budget infinito acidental". Se você quiser um cap por sessão única,
> use `Task.max_usd` na primeira task e deixe-a esgotar.

> **Insight — `tokens_unknown` é honestidade, não punição.**
> Outras ferramentas mostram `$0.00` quando não sabem o custo. O squire
> mostra o gasto conhecido **e** sinaliza explicitamente "o real pode ser
> maior". Reduz surpresas na fatura do provider.

> **Remark — caps não previnem chamadas em andamento.**
> Se um Claude review já começou (5min de latência típica), o cap não
> mata a chamada em curso. Pausa só na **próxima** decisão de chamar.
> Para parar imediatamente: `squire kill` (brutal) ou Ctrl+C (gracioso).

## Próximas leituras

- [Configuração](configuracao.md) — todas as env vars de budget
- [CLI: `squire budget`](cli.md#orçamento) — referência dos subcomandos
- [Tasks](tasks.md#custo-por-task) — `max_usd` no contexto do modelo Task
- [Rate limiting](homologacao.md#rate-limiting) — call count + cost defense in depth
