# Documentação do Squire

🇧🇷 Português · [🇬🇧 English](en/README.md)

Bem-vindo à documentação completa do Squire. Para overview e quickstart,
volte para [README.md](../README.md) na raiz.

## Conceitos

Comece aqui se é a primeira vez:

- **[Arquitetura](arquitetura.md)** — o modelo de dois tiers, componentes,
  fluxo de uma task, e por que o filesystem é tratado como memória.
- **[Tasks](tasks.md)** — a unidade de trabalho: schema JSON, lifecycle,
  effort, TDD, fase RED, e os workflows de autoria via CLI.
- **[Backends](backends.md)** — quem realmente executa o código:
  LiteLLM (HTTP local), OpenCode (CLI com roteamento), Crush (CLI simples).
- **[Homologação](homologacao.md)** — o ciclo de review do Claude Code:
  gate mecânico, detecção de loops, escalações técnicas.
- **[Padrão Viking](padrao-viking.md)** — restrições por domínio em
  `<repo>/docs/viking/*.md` injetadas em cada chamada.

## Operação

Para quem está rodando o squire no dia a dia:

- **[CLI](cli.md)** — referência completa de todos os subcomandos com
  exemplos e output esperado.
- **[Configuração](configuracao.md)** — env vars, `budget.json`,
  `project.json`, tabela de preços, paths e precedência.
- **[Custos e orçamento](custos-e-orcamento.md)** — rastreamento de
  tokens/USD, caps diário e por-task, refunds, comandos `squire budget`.
- **[Estado e recuperação](estado-e-recuperacao.md)** — layout do
  `STATE_ROOT`, escrita atômica, session lock, e cada caminho de recovery.

## Diagnóstico

Quando algo deu errado:

- **[Troubleshooting](troubleshooting.md)** — problemas comuns indexados
  pelo sintoma, com diagnóstico e fix passo a passo.

## Convenções da documentação

- **Source anchors** como `arquivo.py:linha` são referências para o código
  fonte (cole no editor, não são links clicáveis).
- **Callouts** em blockquotes: `> **Insight:** …` para racional de design,
  `> **Remark:** …` para tradeoffs, GitHub alerts (`> [!WARNING]`, etc.)
  para avisos críticos.
- **Cross-links** são relativos (`[CLI](cli.md)`) — funcionam tanto no
  GitHub web quanto em renderers locais (glow, mdcat).
- **Mermaid diagrams** renderizam nativamente no GitHub.
- **EN mirror** em [`en/`](en/) — todos os docs têm versão em inglês com a
  mesma estrutura e source anchors.

## Roadmap

Próximas features documentadas em `/home/ai-debian/.claude/plans/` (fora
do repo, no estado do agente). Inclui: branch + PR automation, codebase
RAG via Qdrant, structured homologation output (file:line:severity), live
dashboard via JSONL events, gate caching, e mais.
