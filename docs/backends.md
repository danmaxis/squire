# Backends

🇧🇷 Português · [🇬🇧 English](en/backends.md)

Squire delega a execução do código para um **backend** — um adapter que
recebe uma instrução textual e devolve os arquivos modificados. Três
backends são suportados hoje: **LiteLLM**, **OpenCode**, **Crush**. A
interface comum é `CodingBackend` em [`backends.py:134`](../backends.py).

## Sumário

- [Comparação](#comparação)
- [LiteLLM](#litellm)
- [OpenCode](#opencode)
- [Crush](#crush)
- [Aider (deprecated)](#aider-deprecated)
- [LLM Lock](#llm-lock)
- [Escolhendo um backend](#escolhendo-um-backend)

## Comparação

| Característica          | LiteLLM                       | OpenCode                              | Crush                          |
| ----------------------- | ----------------------------- | ------------------------------------- | ------------------------------ |
| Como roda               | HTTP API (LiteLLM gateway)    | CLI `opencode run --agent <a> -- ...` | CLI `crush run --cwd ... --yolo` |
| Roteamento de agente    | —                             | `code` / `debug` / `terminal` / `build` | (sem roteamento)             |
| Aplica arquivos como    | Parser de fences `filepath:`  | Edita arquivos direto                  | Edita arquivos direto          |
| Reporta token usage     | ✓ (campo `usage` na resposta) | ✗ (`tokens_unknown=true`)              | ✗ (`tokens_unknown=true`)     |
| Custo típico            | $0 (modelo local)             | Dep. do provider (OPENAI_API_KEY/etc.) | Dep. do provider              |
| Timeout default         | 1200s (`SQUIRE_INNER_TIMEOUT`)| 1200s                                  | 1200s                          |
| Setup necessário        | LiteLLM gateway rodando       | `opencode` no PATH + API key           | `crush` no PATH                |
| ANSI no stdout          | —                             | —                                      | Removido via regex             |
| Stdin para prompt       | (não aplica — HTTP)           | (via `-- "<prompt>"`)                  | ✓ (evita ARG_MAX)              |

## LiteLLM

Backend que chama um LLM via HTTP no formato OpenAI-compatible. Funciona
com qualquer endpoint compatível: gateway LiteLLM, **Ollama** (`/v1`) ou
llama.cpp server. No setup atual do squire, é o Ollama no Zordon
(`http://192.168.50.24:11434/v1`) servindo `journal-synth:latest` (Qwen 35B).

### Como funciona

[`backends.LiteLLMBackend`](../backends.py):

1. Monta payload com `system_prompt` + a instrução do usuário
2. POST em `{base_url}/chat/completions` com retry em falhas de rede (5/10/20s backoff)
3. Lê `choices[0].message.content` e (se presente) `reasoning_content`
   (Qwen3 com `--reasoning-budget` retorna chain-of-thought separado)
4. Parseia o texto procurando fences markdown e escreve arquivos:

```text
```filepath:src/foo.ts
// conteúdo completo do arquivo
```
```

5. Extrai `usage.{prompt,completion}_tokens` da resposta e popula `TokenUsage`
   com custo calculado via tabela de preços

### Formato de fences aceito

`_extract_filepath` ([`backends.py:359`](../backends.py)) reconhece quatro formatos:

```text
```filepath:src/foo.ts        # padrão recomendado
```typescript:src/foo.ts      # alternativa Qwen
src/foo.ts                    # caminho na linha ANTES do fence
```typescript
```Dockerfile                 # arquivos conhecidos sem extensão
```
```

### Validação de caminhos

Todo candidato a caminho passa por `_is_plausible_relpath` antes de virar
arquivo: relativo, sem espaços/metacaracteres de shell (`#`, `"`, `=`…),
sem `..`/absolutos, com extensão ou nome conhecido (Dockerfile etc.).
Linhas soltas que o Qwen derrama fora dos fences (`pytest==8.0.0`,
`# src`, `rm -rf "`) são ignoradas com um aviso no log em vez de virar
arquivos-lixo no repo. `_write_file` revalida e confina a escrita ao
diretório do projeto (defesa em profundidade contra traversal).

### Erros HTTP acionáveis

Falhas 4xx não fazem retry e chegam com mensagem apontando a correção:
401/403 → "verifique `SQUIRE_LITELLM_KEY`"; 404 → "modelo X não
encontrado em <endpoint> — verifique `SQUIRE_LITELLM_MODEL`"; conexão
recusada → "endpoint LLM inacessível em <url> — o serviço está rodando?".

### System prompt

Hardcoded em [`backends.py:32`](../backends.py):

```text
Você é um desenvolvedor experiente num loop de CI automatizado.
O código que você escrever será compilado e testado imediatamente.
Retorne arquivos completos usando o formato ```filepath:caminho/arquivo.ext
(sem texto fora dos blocos de código, sem TODOs, sem esqueletos).
Implemente funcionalidade completa e funcional.
```

### Quando usar

- LLM local rodando (Zordon + GPU dedicada)
- Você quer custo $0 por chamada e privacidade total
- O modelo local é capaz para a complexidade média do projeto
- Quer instrumentação completa (tokens visíveis)

> **Insight — system prompt fixo.**
> O LiteLLM backend não aceita `system_prompt` por-task. Estilo de output
> é uniforme — o squire conta com ele para parsear arquivos. Se você
> precisa de comportamento diferente, instancie `LiteLLMBackend(system_prompt=...)`
> programaticamente, mas tenha em mente que o parser de fences depende do
> formato declarado.

## OpenCode

Backend que delega para o CLI [opencode](https://opencode.ai). Em vez de
parsear output e escrever arquivos, o `opencode` edita o filesystem
diretamente. O squire detecta as mudanças via `git diff --name-only`.

### Como funciona

[`backends.OpenCodeBackend`](../backends.py):

1. Seleciona um agente especializado (ver abaixo)
2. Invoca `opencode run --agent <agent> -- "<prompt>"` com o `cwd` do projeto
3. Após terminar, lê arquivos modificados via `git diff` + `git ls-files --others`
4. Filtra para arquivos de código (exclui `node_modules`, `dist`, etc.)
5. Marca `usage.tokens_unknown=True` (CLI não expõe contadores)

### Roteamento de agentes

`_select_agent` ([`backends.py:427`](../backends.py)) escolhe entre:

| Agente     | Quando dispara                                                                                              |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| `debug`    | `last_error` contém marcador de stack trace real (`traceback`, `error:`, `TypeError`, `at `, etc.)         |
| `terminal` | Título da task COMEÇA com verbo operacional: `run`, `migrate`, `seed`, `init`, `deploy`, `start`, `stop`   |
| `build`    | Título EXATAMENTE em allow-list: `"scaffold project"`, `"setup project"`, `"configure ci"`, etc.            |
| `debug` (fallback) | `attempts >= 6` (LLM empacou sem erro claro — usa debugger como último recurso)                  |
| `code`     | Default — para qualquer implementação de feature                                                            |

> **Insight — anti-falsos-positivos.**
> O `_select_agent` original usava substring matching ("fix" em qualquer
> lugar do título → `debug`, "check" → `terminal`). Resultado: "getCheckpoint"
> virava `terminal`, qualquer task com "fix" virava `debug`. A versão atual
> exige marcadores **reais** de stack trace, **começo** do título para
> verbos operacionais, ou match exato para tarefas de build. Histórico
> do bug em `squire_feedback_session_2026-03-29.md`.

### Quando usar

- Projeto usa stack (TypeScript, Python, Go) já conhecida pelo `opencode`
- Você tem `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (opencode usa providers
  externos por baixo)
- Quer agente especializado por situação (debug vs implementação)
- Custo do provider é aceitável

> **Remark — `tokens_unknown` não significa grátis.**
> O `opencode` chama providers pagos por baixo. O squire mostra `$0.000`
> + `⚠ tokens_unknown`. Confira a fatura no console do provider.

## Crush

Backend que delega para o CLI [crush](https://github.com/charmbracelet/crush).
Similar ao OpenCode mas sem roteamento de agentes — mais simples e mais
previsível.

### Como funciona

[`backends.CrushBackend`](../backends.py):

1. Invoca `crush run --cwd <project> --quiet --yolo` com o prompt via stdin
2. Remove escape codes ANSI do stdout
3. Detecta arquivos modificados via `git diff` + `git ls-files --others`
4. Marca `usage.tokens_unknown=True`

A flag `--yolo` desliga prompts de confirmação interativa (crush executa
diretamente). `--quiet` reduz output decorativo. Prompt via stdin
(`input=instruction` no `subprocess.run`) evita o limite ARG_MAX do kernel
para prompts longos.

### Quando usar

- Você quer comportamento previsível sem roteamento de agentes (`agent_used`
  sempre é `"crush"`)
- O agente único do crush é suficiente para o projeto
- Você quer um backend mais simples para depurar problemas com opencode

## Aider (deprecated)

`AiderBackend` foi descontinuado em 2026-03-29. Tentativas de usar
`squire new --backend aider` ou `create_backend("aider")` levantam:

```text
ValueError: Backend 'aider' foi descontinuado (2026-03-29).
Use 'opencode' ou 'litellm'.
Motivo: aider sobrescreveu tsconfig.json, criou artefatos .js e
oscilou sem convergir em sessão real.
```

A variável `SQUIRE_AIDER_BIN` ainda existe em `config.py` para
backward-compat de checkpoints antigos, mas não tem mais efeito.

> **Remark — por que descontinuei aider.**
> Em sessão real, o aider sobrescreveu `tsconfig.json` com defaults
> incompatíveis, criou artefatos `.js` ao lado dos `.ts`, e oscilou entre
> duas implementações sem convergir após 12 rodadas. O opencode + crush
> não exibiram nenhum desses padrões. Detalhes na sessão de feedback de
> 2026-03-29 (commit `1d4a9b5`).

## LLM Lock

Todos os backends adquirem um `_LLMLock` antes de invocar o modelo:

```python
class _LLMLock:
    """Context manager que adquire um flock exclusivo antes de chamar o LLM."""
    # ...
```

[`backends.py:100`](../backends.py). É um `flock` exclusivo em
`$SQUIRE_STATE_ROOT/llm.lock`. Garante que **apenas um backend chama um LLM
por vez** — evita saturar CPU/GPU quando múltiplas ferramentas estão
rodando (ex: orchestrator + um aider standalone + opencode interativo).

Calls em paralelo simplesmente esperam o lock. Sem timeout (intencional —
melhor esperar do que falhar).

## Escolhendo um backend

### Por projeto

Em `project.json`:

```json
{
  "id": "my-app",
  "coding_backend": "opencode"
}
```

Sobrescreve `SQUIRE_CODING_BACKEND` para este projeto.

### Globalmente

Env var:

```bash
export SQUIRE_CODING_BACKEND=litellm   # default global
```

### Mudando mid-projeto

Edite `project.json`. O squire lê de novo a cada sessão. Não há migração
necessária — o `BackendResult` é uniforme.

### Heurística rápida

- **Comece com `opencode`** — o squire usa como default. Funciona out-of-the-box
  se você já tem API keys configuradas no shell.
- **Mude para `litellm`** se você quer custo $0 e tem o LiteLLM gateway
  rodando localmente.
- **Mude para `crush`** se opencode escolhe agentes errados muito frequentemente
  para o seu tipo de task (ou se você está depurando o roteamento).

## Próximas leituras

- [Configuração](configuracao.md) — env vars relacionadas a backends
- [Arquitetura](arquitetura.md) — onde o backend fica no fluxo geral
- [Custos e orçamento](custos-e-orcamento.md) — `tokens_unknown` em detalhe
- [Tasks: effort](tasks.md#effort-e-roteamento-de-modelo) — `effort` controla
  qual modelo o LiteLLM usa
