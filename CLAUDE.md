# CLAUDE.md — Squire Project Briefing

Este arquivo é o briefing completo do projeto para o Claude Code.
Leia integralmente antes de qualquer ação.

## Visão geral

Este projeto implementa um **squire** que coordena dois tiers de LLM
para executar projetos de software de forma semi-autônoma:

- **Tier 1 (execução)**: LLM local (Qwen) faz implementação, refatoração e
  correção de código até passar nos testes.
- **Tier 2 (supervisão)**: Claude Code faz homologação de alto nível
  (review de engenharia), escalação técnica quando o local empaca,
  e planejamento inicial de projetos.

A proporção-alvo é **30 chamadas locais para cada 1 do Claude Code**.

O primeiro projeto conduzido pelo orquestrador é o **Orchestrator Dashboard**:
uma página Next.js que mostra o estado dos projetos em tempo real, lendo
arquivos JSON do filesystem. É o projeto se observando nascer.

## Infraestrutura

### Servidor — Zordon (Unraid)
- **Host**: `192.168.50.24` (rede local)
- **CPU**: Ryzen 7 5700G
- **GPU**: RTX 3090 (24GB VRAM) — usada pelo llama.cpp
- **SO**: Unraid, containers Docker

### VM — Ai-Debian
- Roda no Zordon como VM Debian
- É onde o Claude Code opera e onde o squire executa
- Tem acesso ao filesystem do Unraid via mount

### LLM local — Qwen via LiteLLM
- **llama.cpp** roda no Zordon com o modelo `Qwen3.5-35B-A3B-Q4_K_M`
- **LiteLLM** é o API gateway: `http://192.168.50.24:4000/v1`
- **Model alias**: `journal-synth` (aponta pro Qwen)
- **API key**: `sk-local` (placeholder, LiteLLM local não exige auth real)
- **Flags do llama.cpp**: `-fa on -ctk q8_0 -ctv q8_0 -ngl all --reasoning-budget -1 --cache-reuse 256`
- **Performance**: ~124 tok/s com reasoning_content visível

### Filesystem de estado
```
/mnt/user/data/squire/                ← raiz do estado persistente
├── session.lock                      ← lock global do squire
├── rate.json                         ← budget diário
├── alerts.json                       ← alertas ativos
├── global-stats.json                 ← métricas agregadas
├── projects/
│   ├── orchestrator-dashboard/       ← projeto-piloto
│   │   ├── project.json
│   │   ├── tasks.json
│   │   ├── history.json
│   │   ├── commits.json
│   │   └── checkpoint.json
│   └── {outro-projeto}/
│       └── ...
```

Os JSONs são o **contrato** entre o squire e o dashboard.
O dashboard é **read-only** — só lê esses arquivos via polling a cada 30s.

### Serviços existentes no Zordon (Docker)
Já estão rodando e podem ser usados pelos projetos:
- **PostgreSQL** — bancos/schemas dedicados por projeto (o squire gerencia pra não colidir)
- **Qdrant** — vector search
- **Redis** — cache (se necessário)
- **Grafana** — dashboards de infra
- **Cloudflare Tunnel** — expõe serviços via `*.danmaxis.dev.br`
- **Syncthing** — sync de arquivos
- **n8n** — workflow automation (usado pelo sistema de journal, não pelo squire)

### O que NÃO fazer no Unraid
> **REGRA CRÍTICA**: O Claude Code NÃO deve criar, modificar ou deletar
> containers Docker no Unraid. Se precisar de um novo container (ex: o
> container do dashboard Next.js), descreva o que precisa (imagem, volumes,
> portas, env vars) e peça ao operador humano (Danilo) para criar.

## Arquitetura do squire

### Fluxo principal
```
1. Ler checkpoint.json (ou criar novo)
2. Adquirir session.lock
3. Para cada task pendente:
   a. Inner loop: LLM local implementa + testa (até 10 tentativas)
      - A cada 5 falhas consecutivas → escalação técnica ao Claude Code
   b. Se testes passam → homologação pelo Claude Code (até 3 tentativas)
      - Se rejeitada → feedback volta pro inner loop, tenta de novo
   c. Se aprovada → task concluída, avança cursor
   d. Se 3 rejeições → bloqueia task, gera alerta, segue pra próxima
4. Checkpoint persistido a cada transição de estado
5. Ao final, libera lock e atualiza stats
```

### Módulos do código
- `squire.py` — loop principal, ponto de entrada CLI
- `models.py` — schemas Pydantic v2 (checkpoint, tasks, alerts, etc.)
- `checkpoint.py` — leitura/escrita atômica de estado + lock management
- `inner_loop.py` — interface com LLM local via LiteLLM HTTP API
- `homologator.py` — interface com Claude Code via `claude --print`
- `rate_limiter.py` — controle de janela deslizante para calls ao Claude Code
- `config.py` — paths, endpoints, knobs (tudo sobrescrevível via env vars)

### Design do checkpoint (inspirado no Manus)
O filesystem é tratado como memória externalizada. O `checkpoint.json` salva:
- **cursor**: qual task, subtask, passo (llm_execution/testing/homologation), tentativa
- **llm_context_summary**: resumo compacto (não o histórico completo) — última instrução,
  arquivos tocados, último erro, estado dos testes
- **rate_limit**: calls na janela atual
- **recovery_hints**: se pode retomar e como

Escrita atômica: temp file → `os.replace()` (atômico no mesmo filesystem).

### Rate limiting
- **Máximo**: 10 chamadas ao Claude Code a cada 30 minutos
- Se exceder, o orquestrador **pausa** e aguarda a janela resetar
- O LLM local continua trabalhando independente do rate limit
- Configurável via env vars: `SQUIRE_CC_MAX_CALLS`, `SQUIRE_CC_WINDOW_MIN`

### Escalação técnica vs. homologação
São duas interações diferentes com o Claude Code:
- **Homologação**: review de alto nível. "O código resolve o que a task pede?
  Tem edge cases? É legível?" Resultado: approved/rejected com feedback.
- **Escalação técnica**: debugging. "O LLM local está empacado nesse erro há
  5 tentativas, me ajuda a desbloquear." Resultado: instruções que voltam
  pro LLM local como extra_instructions.

## Projeto-piloto: Orchestrator Dashboard

### Stack
- **Next.js** (App Router) + TypeScript + Tailwind CSS
- Desenvolvido na VM Ai-Debian, deploy como container Docker no Unraid

### Funcionalidades
1. **R1** — Listagem de projetos com status visual (badge colorido)
2. **R2** — Detalhe com timeline de histórico de tentativas/homologações
3. **R3** — Alertas de intervenção destacados no topo
4. **R4** — Resumo de últimos commits com diff summary
5. **R5** — Métricas globais: total projetos, tasks completas,
   calls local vs Claude Code, taxa de aprovação 1ª homologação
6. **R6** — Auto-refresh via polling a cada 30s (sem WebSocket)

### Fonte de dados
O dashboard lê os JSONs do filesystem. Em dev, pode apontar pra um
diretório local com dados de exemplo. Em produção, monta o volume
`/mnt/user/data/squire/` (read-only).

### Tasks do projeto
Ver `projects/orchestrator-dashboard/tasks.json` para o backlog completo.

## Convenções

### Idioma
- Código: **inglês** (nomes de variáveis, funções, classes, commits)
- Comentários e docstrings: **português** quando explicam contexto de negócio,
  inglês quando são técnicos puros
- Documentação (README, CLAUDE.md): **português**

### Estilo de código (Python)
- Python 3.11+
- Pydantic v2 para schemas
- Type hints em todas as funções públicas
- f-strings para formatação
- `from __future__ import annotations` no topo de cada arquivo
- Sem classes quando uma função resolve
- Imports organizados: stdlib → third-party → local

### Estilo de código (TypeScript/React — dashboard)
- Next.js App Router (não Pages)
- Server components por padrão, client components só quando precisa de interatividade
- Tailwind para styling (sem CSS modules)
- Tipos explícitos, sem `any`
- Componentes funcionais, hooks quando necessário

### Git
- Branches: `feat/<nome>`, `fix/<nome>`, `chore/<nome>`
- Commits: conventional commits em inglês
  - `feat: add project card component`
  - `fix: handle empty task list in timeline`
  - `chore: update dependencies`
- Commitar a cada task concluída (não a cada subtask)
- Não commitar diretamente na `main` — usar branches + merge

### Estrutura de diretórios (dashboard)
```
orchestrator-dashboard/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              ← lista de projetos + alertas + métricas
│   │   └── project/[id]/
│   │       └── page.tsx          ← detalhe do projeto
│   ├── components/
│   │   ├── ProjectCard.tsx
│   │   ├── AlertBanner.tsx
│   │   ├── GlobalStats.tsx
│   │   ├── TaskList.tsx
│   │   ├── Timeline.tsx
│   │   ├── CommitLog.tsx
│   │   └── StatusBadge.tsx
│   ├── lib/
│   │   ├── types.ts              ← tipos espelhando models.py
│   │   ├── data.ts               ← funções para ler JSONs
│   │   └── constants.ts
│   └── hooks/
│       └── useAutoRefresh.ts     ← polling hook
├── public/
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
├── Dockerfile
└── docker-compose.yml
```

## Variáveis de ambiente

### Squire (Python)
```bash
SQUIRE_STATE_ROOT=/mnt/user/data/squire
SQUIRE_LITELLM_URL=http://192.168.50.24:4000/v1
SQUIRE_LITELLM_MODEL=journal-synth
SQUIRE_LITELLM_KEY=sk-local
SQUIRE_INNER_MAX_ATTEMPTS=10
SQUIRE_INNER_TIMEOUT=300
SQUIRE_CLAUDE_BIN=claude
SQUIRE_CC_MAX_CALLS=10
SQUIRE_CC_WINDOW_MIN=30
SQUIRE_MAX_HOMOLOG=3
SQUIRE_LOCK_TTL=60
SQUIRE_HEARTBEAT=300
```

### Dashboard (Next.js)
```bash
ORCHESTRATOR_DATA_PATH=/mnt/user/data/squire
NEXT_PUBLIC_REFRESH_INTERVAL=30000
```

## Como executar

### Squire
```bash
cd /caminho/do/squire
python squire.py orchestrator-dashboard          # execução normal
python squire.py orchestrator-dashboard --dry-run # simula sem executar
python squire.py orchestrator-dashboard --resume  # retoma de crash
```

### Dashboard (dev)
```bash
cd /caminho/do/orchestrator-dashboard
npm install
npm run dev
```

### Dashboard (produção)
```bash
docker build -t orchestrator-dashboard .
# Pedir ao Danilo para criar o container no Unraid com:
#   - Imagem: orchestrator-dashboard
#   - Porta: 3100:3000
#   - Volume: /mnt/user/data/squire:/data:ro
#   - Env: ORCHESTRATOR_DATA_PATH=/data
```

## Notas para o Claude Code

1. **Você é o tech lead**. Planeja, revisa, e decide. O trabalho braçal de
   implementação vai pro LLM local via inner loop do squire.

2. **Não assuma o que não está escrito**. Se algo não está neste arquivo,
   pergunte ao Danilo antes de inventar.

3. **Incremental sempre**. Prefira mudanças pequenas que funcionam a mudanças
   grandes que podem quebrar. Teste cada peça isoladamente antes de integrar.

4. **O filesystem é sua memória**. Use o checkpoint e os JSONs de estado
   como fonte da verdade. Não confie no contexto da sessão para estado
   de longo prazo.

5. **Cuide do budget**. Cada interação sua custa mais que 30 do LLM local.
   Só peça para ser chamado quando o valor agregado justifica.

6. **Commits são seu registro**. Cada commit deve ser autocontido e com
   mensagem descritiva. Se alguém ler o git log, deve entender a história
   do projeto sem abrir os arquivos.
