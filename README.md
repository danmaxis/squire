# Squire — Claude Code + LLM Local

Sistema de orquestração que coordena Claude Code (planejamento e homologação)
com um LLM local (implementação) para execução semi-autônoma de projetos.

> Para o briefing completo usado pelo Claude Code, ver [CLAUDE.md](./CLAUDE.md).

## Quickstart

```bash
# Instalar dependências
pip install -e ".[dev]"

# Dry run (simula sem executar LLMs)
python squire.py orchestrator-dashboard --dry-run

# Execução real
python squire.py orchestrator-dashboard

# Retomar após crash
python squire.py orchestrator-dashboard --resume
```

## Estrutura do projeto

```
squire/
├── CLAUDE.md            # Briefing completo para o Claude Code
├── squire.py            # Loop principal — ponto de entrada CLI
├── models.py            # Schemas Pydantic v2 (checkpoint, tasks, etc.)
├── checkpoint.py        # Leitura/escrita atômica de estado + lock
├── inner_loop.py        # Interface com LLM local via LiteLLM
├── homologator.py       # Interface com Claude Code para homologação
├── rate_limiter.py      # Controle de rate limit do Claude Code
├── config.py            # Configuração centralizada (env vars)
├── pyproject.toml       # Dependências e configuração do projeto
├── .gitignore
├── projects/            # Estado inicial dos projetos
│   └── orchestrator-dashboard/
│       ├── project.json
│       ├── tasks.json   # 11 tasks do projeto-piloto
│       ├── history.json
│       └── commits.json
└── fixtures/            # Dados de exemplo para desenvolvimento do dashboard
    └── data/            # Espelha a estrutura de /mnt/user/data/squire/
        ├── alerts.json
        ├── global-stats.json
        └── projects/
            ├── orchestrator-dashboard/
            └── api-gateway/
```

## Fluxo

1. Lê checkpoint (ou cria novo)
2. Adquire session lock
3. Para cada task pendente:
   a. Inner loop: LLM local implementa + testa (até 10 tentativas)
   b. A cada 5 falhas → escalação técnica ao Claude Code
   c. Homologação: Claude Code valida (até 3 tentativas)
   d. Se aprovado → próxima task
   e. Se 3 rejeições → alerta + bloqueia + segue pra próxima
4. Checkpoint persistido a cada transição de estado

## Ambiente

- **VM**: Ai-Debian no Unraid (Zordon)
- **LLM local**: Qwen 3.5 35B via LiteLLM em `192.168.50.24:4000/v1`
- **Estado persistente**: `/mnt/user/data/squire/`
- **Claude Code**: instalado na VM, invocado via `claude --print`

## Projeto-piloto

O primeiro projeto é o **Orchestrator Dashboard**: uma página Next.js que
mostra o estado dos projetos conduzidos pelo squire. As 11 tasks
estão definidas em `projects/orchestrator-dashboard/tasks.json`.

Os fixtures em `fixtures/data/` simulam um cenário realista com dois projetos
em estágios diferentes, para desenvolvimento do dashboard sem depender do
squire rodando.
