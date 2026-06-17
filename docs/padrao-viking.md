# Padrão Viking

🇧🇷 Português · [🇬🇧 English](en/viking-pattern.md)

O **Padrão Viking** é um mecanismo simples para injetar **restrições de
domínio** em todas as chamadas do squire para um projeto: linting, padrões
de banco de dados, convenções de estilo, proibições específicas. Você
escreve as regras em arquivos Markdown dentro do repo do projeto; o squire
as carrega automaticamente.

## Sumário

- [Como funciona](#como-funciona)
- [Estrutura no repo](#estrutura-no-repo)
- [Quando é injetado](#quando-é-injetado)
- [Limites](#limites)
- [Exemplos](#exemplos)
- [Insights e remarks](#insights-e-remarks)

## Como funciona

[`viking.py`](../viking.py) — implementação inteira em ~90 linhas.

`load_viking_context(project_repo_path)` procura por
`<repo>/docs/viking/*.md`, concatena, e retorna como bloco de texto.
O squire (inner loop e homologator) injeta esse bloco no prompt antes
de cada chamada relevante:

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

Mesma injeção em `homologator._build_review_prompt`. O Claude e o LLM local
veem as mesmas regras.

## Estrutura no repo

Dentro do `repo_path` do projeto (não no STATE_ROOT):

```text
<repo_path>/
└── docs/
    └── viking/
        ├── stack_python.md       ← regras de tipagem, estilo
        ├── banco_dados.md        ← padrões SQL, migrações
        ├── api_design.md         ← convenções REST/GraphQL
        └── (outros domínios)
```

Os nomes dos arquivos são livres — o squire carrega todos os `*.md` em
ordem alfabética.

## Quando é injetado

| Caminho                                  | Injeta? |
| ---------------------------------------- | ------- |
| Inner loop — instrução para o backend    | ✓       |
| Homologator — prompt de review do Claude | ✓       |
| Escalação `unblock` / `implement_directly`| Indireto (recebe via contexto, mas não relê viking) |
| Fase RED (escrita de testes)             | Não atualmente — futuro |
| `squire tasks plan`                      | Não — plan não acessa o repo |

## Limites

`max_chars` (default 3000) protege contra prompts gigantes. Quando excede,
o squire **trunca o último arquivo** (não os anteriores) e adiciona `…`
para sinalizar truncamento.

```python
# viking.py:66
if total + len(block) > max_chars:
    remaining = max_chars - total - len(header) - 2
    if remaining > 100:
        parts.append(f"{header}\n{content[:remaining]}…")
    break
```

> **Remark — ordem importa.**
> Como o último arquivo pode ser truncado, **coloque o que é mais
> importante nos primeiros** (alfabeticamente). Por exemplo, prefixe
> arquivos críticos com `00-`, `01-`:
> ```text
> docs/viking/
> ├── 00-proibicoes.md       ← lido sempre, completo
> ├── 01-style_guide.md      ← lido sempre, completo
> └── nice_to_have.md        ← pode ser truncado
> ```

## Exemplos

### `docs/viking/stack_python.md`

```markdown
# Stack Python — regras

- Python 3.11+ obrigatório.
- `from __future__ import annotations` no topo de TODO arquivo .py.
- Type hints em todas as funções públicas (módulo-level e classes).
- Não use `Optional[X]` — use `X | None` (PEP 604).
- Pydantic v2 para schemas (não v1).
- `pytest` para testes, sem `unittest`.
- f-strings para formatação. Nunca `%`-formatting ou `.format()`.
- Imports organizados: stdlib, third-party, local — separados por linha em branco.
- Linhas até 100 chars (não 79).
- Sem classes quando uma função resolve.
```

### `docs/viking/banco_dados.md`

```markdown
# Banco de dados — regras

- Postgres 15+. Sem MySQL.
- Migrations via Alembic, nunca DDL inline em código de aplicação.
- IDs inteiros sequenciais (BIGSERIAL), não UUID.
- Toda tabela tem `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`.
- Toda tabela tem `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` + trigger de atualização.
- Soft delete via `deleted_at TIMESTAMPTZ NULL`, NUNCA `DELETE` físico.
- FKs sempre `ON DELETE RESTRICT` (queremos saber se algo depende).
- Índices nomeados explicitamente: `idx_<table>_<columns>`.

PROIBIDO:
- `SELECT *` em produção (use colunas explícitas).
- `JOIN` sem alias.
- ORM lazy loading sem N+1 check.
```

### `docs/viking/api_design.md`

```markdown
# API Design — convenções REST

- Path em kebab-case: `/api/users/active-sessions`, não `/api/users/activeSessions`.
- Verbos HTTP corretos: POST = criar, PUT = substituir, PATCH = mutar, DELETE = remover.
- 2xx para sucesso, 4xx para erro do cliente, 5xx para erro do servidor.
- 404 deve ter body JSON `{"error": "not_found", "message": "..."}`, NUNCA HTML.
- Lista sempre paginada: `?page=1&per_page=20`, retornando `{data, meta: {total, page, pages}}`.
- Timestamps em ISO 8601 UTC com Z final, NUNCA epoch ou timezone local.
- IDs em path quando referenciados, NUNCA em query string.
```

## Insights e remarks

> **Insight — Viking é advisory, não enforced.**
> O padrão NÃO impede o LLM de violar as regras. Ele só as coloca no
> prompt. O LLM tende a respeitar instruções explícitas, mas pode falhar.
> O gate mecânico ([Homologação](homologacao.md#gate-mecânico-pré-homologação))
> pega violações específicas que dá para detectar com ferramentas
> (`tsc`, `cargo clippy`); o Viking cobre as **regras que ficam fora
> da capacidade de checkers automáticos** — convenções de estilo,
> proibições específicas do domínio, contexto histórico do projeto.

> **Insight — por que mora no repo, não no STATE_ROOT?**
> Restrições são propriedade do projeto, não do orquestrador. Devem ser
> versionadas no git do projeto, evoluir com o código, e estar disponíveis
> mesmo se você executa o projeto fora do squire. O Viking é apenas um
> padrão para *como ler* essa pasta — qualquer pessoa pode ler
> `docs/viking/*.md` para entender as regras.

> **Insight — origem do nome.**
> "Viking" porque é um padrão de governança: viking-age communities tinham
> *þing* (assembleias) que estabeleciam regras locais antes da execução.
> O squire faz o mesmo: lê as regras antes de cada chamada, e o LLM
> opera dentro delas. O fato de existir uma palavra real (não um acrônimo
> forçado) ajuda a torná-lo memorável.

> **Remark — Viking não é o lugar para descrição da task.**
> Coloque restrições gerais do projeto no Viking. Descrição específica
> do que deve ser feito vai no `task.description` no `tasks.json`. Se
> você se pegar atualizando o Viking para uma feature individual, esse
> conteúdo provavelmente deveria ir na task.

## Próximas leituras

- [Homologação](homologacao.md) — quando o gate mecânico pega o que o Viking não pega
- [Tasks](tasks.md) — onde descrever escopo da task vs onde colocar restrições gerais
- [Arquitetura](arquitetura.md) — onde o Viking se encaixa no prompt
