# Troubleshooting

🇧🇷 Português · [🇬🇧 English](en/troubleshooting.md)

Problemas comuns + diagnóstico + fix. Organizado pelo sintoma observável,
não pela causa raiz.

> **Comece pelo doctor.** Antes de caçar a causa manualmente, rode
> `squire doctor` — ele verifica endpoint do LLM, binários, locks e
> sanidade dos projetos de uma vez, e aponta o comando de correção
> para os problemas que reconhece. `squire doctor --fix` limpa locks
> comprovadamente mortos.

## Sumário

- ["Outra sessão está ativa" no startup](#outra-sessão-está-ativa-no-startup)
- [Lock residual depois de Ctrl+C ou crash](#lock-residual-depois-de-ctrlc-ou-crash)
- [Task ficou `blocked` após várias rodadas](#task-ficou-blocked-após-várias-rodadas)
- [OpenCode escolheu o agente errado](#opencode-escolheu-o-agente-errado)
- ["Custo real provavelmente maior" no summary](#custo-real-provavelmente-maior-no-summary)
- [Budget esgotado e não quero esperar até midnight UTC](#budget-esgotado-e-não-quero-esperar-até-midnight-utc)
- [Testes passando mas gate reprova](#testes-passando-mas-gate-reprova)
- [Loop detectado mas não escala](#loop-detectado-mas-não-escala)
- [Qwen retorna texto fora dos fences](#qwen-retorna-texto-fora-dos-fences)
- [Sessão lenta para inicializar](#sessão-lenta-para-inicializar)
- [Auto-snapshot commit não acontece](#auto-snapshot-commit-não-acontece)

## "Outra sessão está ativa" no startup

**Sintoma:**

```text
$ squire run my-app
⚠ Sessão ativa (PID 28471). Use 'squire kill' para encerrar.
```

**Diagnóstico:** já existe uma sessão em execução, OU há lock residual
de uma sessão anterior cujo processo morreu.

**Fix:**

```bash
$ squire status      # quem é o holder, PID está vivo?
# Se PID vivo e for outra sessão sua: deixe rodar ou Ctrl+C nela
# Se PID morto:
$ squire unlock      # remove só o lock
# Se PID vivo mas travado:
$ squire kill        # mata processo + remove lock
```

## Lock residual depois de Ctrl+C ou crash

**Sintoma:** `squire status` mostra "Lock residual (processo morto)".

**Diagnóstico:** o processo morreu antes do `finally` que libera o lock —
SIGKILL, OOM, kernel panic, ou Ctrl+C durante shutdown não-gracioso.

**Fix:**

```bash
$ squire unlock
✓ Lock removido.
$ squire resume my-app    # retoma do checkpoint
```

> **Insight — TTL do lock como fail-safe.**
> Se você não rodar `squire unlock`, o lock expira sozinho após
> `SQUIRE_LOCK_TTL` (default 60min). Uma nova sessão pode então tomar
> posse. Use `unlock` se quiser começar imediatamente.

## Task ficou `blocked` após várias rodadas

**Sintoma:**

```text
[14:35:00] ✗ Task bloqueada: task-007
```

E `alerts.json` tem uma entrada `max_homologations_reached` ou `task_budget_exceeded`.

**Diagnóstico:**

- `max_homologations_reached` → atingiu `max_homologation_attempts` sem
  aprovação. Provavelmente loop não resolvido ou edge case persistente.
- `task_budget_exceeded` → `Task.max_usd` (ou `PER_TASK_USD_CAP`) excedido.

**Inspecione o histórico:**

```bash
$ cat $SQUIRE_STATE_ROOT/projects/my-app/history.json \
  | jq '[.events[] | select(.task_id == "task-007") | {ts: .timestamp, type, summary}]'
```

Veja os últimos `homologation_failed.summary` para entender por que o
Claude estava rejeitando.

**Fix:**

- Se o problema é claro e você consegue corrigir (ex: descrição da task
  ambígua): edite a task e `squire unblock`:
  ```bash
  $ squire tasks edit my-app task-007
  $ squire unblock my-app task-007
  ```
- Se o trabalho está corrompido e você quer começar de novo:
  ```bash
  $ squire reset my-app task-007    # descarta código + reseta
  ```
- Se foi cap USD: aumente o cap na task ou globalmente e desbloqueie.
- Depois de resolver, reconheça o alerta correspondente:
  ```bash
  $ squire alerts list
  $ squire alerts ack --project my-app --task task-007
  ```

## OpenCode escolheu o agente errado

**Sintoma:** task de implementação está usando `debug` agent (ou `terminal`)
e produzindo output bizarro.

**Diagnóstico:** o `_select_agent` ([`backends.py:338`](../backends.py))
casou com uma regra que não deveria. As regras atuais já evitam falsos
positivos comuns, mas o título pode estar enganando o regex.

**Fix temporário:** mude o título da task para não casar com os padrões:

- `terminal` é acionado quando o título **começa com** `run|migrate|seed|init|deploy|start|stop|restart`. Reescreva: `"run migration"` → `"adicionar migration de users"`.
- `debug` é acionado quando `last_error` contém marcadores de stack trace.
  Não dá para mudar — é a base do roteamento. Se inadequado, troque o backend
  para `crush` (sem roteamento).

**Fix de longo prazo:** abra issue / PR ajustando regras em
`backends.py:_select_agent` com o novo caso.

## "Custo real provavelmente maior" no summary

**Sintoma:**

```text
⚠ 3 chamada(s) sem usage reportado — custo real pode ser maior
```

**Diagnóstico:** `tokens_unknown=True` em pelo menos uma chamada. Os
backends `opencode` e `crush` não expõem contagens de tokens no stdout
de forma confiável, então o squire registra `cost_usd=0` mas marca a
flag.

**Não é um bug.** É honestidade. Se você quer rastreamento real de custo
para esses backends, confira a fatura do provider (Anthropic / OpenAI
console).

**Para evitar a warning:** use backend `litellm` (que reporta usage
corretamente) ou ignore — a flag é informativa.

## Budget esgotado e não quero esperar até midnight UTC

**Sintoma:**

```text
[budget] ✗ Budget diário esgotado ($10.05/$10.00) — pausando até midnight UTC
```

**Fix:**

Opção 1 — aumente o cap:

```bash
$ squire budget set --daily 20
✓ Budget atualizado em /home/ai-debian/squire-state/budget.json
  daily_usd:    $20.00
$ squire resume my-app
```

Opção 2 — reset os contadores (faz a casa começar do zero, mas você perdeu
o histórico do dia):

```bash
$ squire budget reset
✓ Contadores diários resetados para 2026-05-11
$ squire resume my-app
```

> **Remark — `reset` apaga histórico do dia em `global-stats.json`.**
> Os eventos em `history.json` continuam intactos (eles têm timestamps
> próprios). Se você precisa do total real do dia para auditoria,
> some pelos eventos antes de resetar.

## Testes passando mas gate reprova

**Sintoma:** logs mostram "Gate pré-homologação: 1 violation(s)" mesmo
com testes verdes.

**Diagnóstico:** o gate roda checkers que vão além dos testes:

- `tsc --noEmit` pode pegar tipos errados que os testes não exercitam
- `cargo clippy -- -D warnings` trata warnings como erros
- `go vet` detecta padrões problemáticos
- Detecção anti-vibe-coding (novo `: any`, `# type: ignore`, etc.)

**Inspecione o violation:** o log mostra os primeiros 120 chars de cada
violation. Para mais detalhe, edite [`squire.py`](../squire.py) temporariamente
para logar o objeto inteiro, ou rode o tool standalone:

```bash
$ cd $REPO_PATH
$ npx tsc --noEmit          # TypeScript
$ cargo clippy -- -D warnings   # Rust
$ go vet ./...              # Go
```

**Fix:** trate a violation no working tree, commit, e `squire resume`.

## Loop detectado mas não escala

**Sintoma:**

```text
[14:31:00] ✗ Loop detectado: mesmo erro em 3 rejeições consecutivas
[14:31:00] ⚠ Rate limit ativo — não é possível escalar agora
```

**Diagnóstico:** o squire detectou o loop e tentou escalar para o Claude
Code, mas `can_afford` retornou `False` — rate limit ou budget cheio.
O loop continua porque o LLM local não tem como sair sem ajuda.

**Fix:**

- Espere o rate limit resetar (`squire status` mostra `janela reseta em
  Xmin`)
- Ou se for budget: `squire budget set --daily X` (raise) ou `reset`
- Em última instância: `squire kill` e edite a task descrição para clarificar
  o que está faltando, depois `resume`

## Qwen retorna texto fora dos fences

**Sintoma:** `files_touched` está vazio mesmo o Qwen tendo "implementado"
visivelmente no `raw_output`.

**Diagnóstico:** O parser de fences (`LiteLLMBackend._apply_changes`,
[`backends.py:223`](../backends.py)) só reconhece formatos específicos:

```text
```filepath:src/foo.ts
```typescript:src/foo.ts     ← linguagem:caminho
src/foo.ts                   ← caminho na linha antes do fence
```typescript
```

Se o Qwen retornou só ```` ```typescript ```` sem caminho, ou texto puro
sem fence, o parser não cria os arquivos.

**Fix:**

- O system prompt já instrui o formato. Se está falhando consistentemente,
  a culpa é do modelo. Considere trocar para um Qwen com melhor instruction
  following (ou um modelo maior).
- Para uma task específica, edite o `description` para reforçar o formato
  com um exemplo.

## Sessão lenta para inicializar

**Sintoma:** `squire run my-app` demora ≥ 30s para começar a primeira
chamada.

**Diagnóstico possíveis:**

- LiteLLM gateway não está respondendo (timeout no health check). Verifique:
  `curl http://localhost:4000/v1/models`.
- `tasks.json` enorme (centenas de tasks) — Pydantic v2 validation leva alguns
  segundos.
- `STATE_ROOT` num filesystem lento (rede, NFS).
- `progress.txt` grande sendo lido a cada inner loop.

**Fix:**

- Verifique conectividade com o LiteLLM
- Se `tasks.json` grande, considere splitar em projetos menores
- Se `progress.txt` grande, espere a Improvement #C do roadmap
  (rolling summarization)

## Auto-snapshot commit não acontece

**Sintoma:** working tree do projeto fica sujo após uma sessão,
sem commit `chore: auto-snapshot before <task-id>`.

**Diagnóstico:**

- Repo não foi inicializado (`.git/` não existe) — `_auto_snapshot_commit`
  retorna silenciosamente
- Repo existe mas não tem nenhum commit ainda (sem HEAD) — também retorna
- `git add` falhou (permissões, hooks `.gitignore` que excluem demais)

**Fix:**

```bash
$ cd $REPO_PATH
$ ls -la .git           # repo existe?
$ git log --oneline -1  # tem commits?
# Se ambos OK, rodar manualmente para ver o erro:
$ git add -A
$ git commit -m "chore: manual snapshot"
```

Se `git commit` falha por hook, o squire também falha — pode ser hook
mal configurado.

## Quando nada disso ajuda

- **Logs:** verifique `/tmp/squire.log` (modo `bg`) ou a saída terminal direta
- **History:** `cat $SQUIRE_STATE_ROOT/projects/<id>/history.json | jq` —
  o caminho exato dos últimos eventos
- **Checkpoint:** `cat $SQUIRE_STATE_ROOT/projects/<id>/checkpoint.json | jq` —
  o cursor exato + `recovery_hints`
- **Tests:** rode `pytest tests/` na raiz do squire para garantir que
  o código está saudável
- **Issues:** se nada disso resolveu, abra um issue com:
  - Versão do squire (último commit hash)
  - Saída de `squire status`
  - Últimos 30 eventos de `history.json`
  - Comportamento esperado vs observado

## Próximas leituras

- [Estado e recuperação](estado-e-recuperacao.md) — comandos detalhados
- [Custos e orçamento](custos-e-orcamento.md) — gerenciar caps e refunds
- [Backends](backends.md) — diferenças de comportamento entre os 3 backends
