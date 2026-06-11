"""
Configuração centralizada do orquestrador.
Todos os valores podem ser sobrescritos via variáveis de ambiente.
"""

import json
import os
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────

# Raiz do estado persistente (disco local da VM; mesmo default do wrapper bash)
STATE_ROOT = Path(os.getenv("SQUIRE_STATE_ROOT", "/home/ai-debian/squire-state"))

PROJECTS_DIR = STATE_ROOT / "projects"
ALERTS_FILE = STATE_ROOT / "alerts.json"
STATS_FILE = STATE_ROOT / "global-stats.json"
SESSION_LOCK_FILE = STATE_ROOT / "session.lock"
RATE_FILE = STATE_ROOT / "rate.json"
BUDGET_FILE = STATE_ROOT / "budget.json"


def _load_budget_file() -> dict:
    """Lê limites persistidos por `squire budget set`. Env vars têm prioridade."""
    if not BUDGET_FILE.exists():
        return {}
    try:
        return json.loads(BUDGET_FILE.read_text())
    except Exception:
        return {}


_budget = _load_budget_file()


# ── LLM Local (Qwen via LiteLLM) ──────────────────────────────────

LITELLM_BASE_URL = os.getenv(
    "SQUIRE_LITELLM_URL",
    "http://localhost:4000/v1"
)

LITELLM_MODEL = os.getenv(
    "SQUIRE_LITELLM_MODEL",
    "journal-synth"  # alias apontando pro Qwen3.5-35B-A3B
)

# Modelos por nível de complexidade (effort-aware routing)
# Por padrão todos apontam para o mesmo modelo; diferencie via env vars
MODEL_LOW    = os.getenv("SQUIRE_MODEL_LOW",    LITELLM_MODEL)
MODEL_MEDIUM = os.getenv("SQUIRE_MODEL_MEDIUM", LITELLM_MODEL)
MODEL_HIGH   = os.getenv("SQUIRE_MODEL_HIGH",   LITELLM_MODEL)

LITELLM_API_KEY = os.getenv("SQUIRE_LITELLM_KEY", "sk-local")

# Limites do inner loop
INNER_LOOP_MAX_ATTEMPTS = int(os.getenv("SQUIRE_INNER_MAX_ATTEMPTS", "10"))
INNER_LOOP_TIMEOUT_SECONDS = int(os.getenv("SQUIRE_INNER_TIMEOUT", "1200"))

# Backend de coding agent (litellm | opencode)
# DEPRECATED: 'aider' foi descontinuado em 2026-03-29 — use 'opencode' ou 'litellm'
CODING_BACKEND = os.getenv("SQUIRE_CODING_BACKEND", "opencode")
AIDER_BIN = os.getenv("SQUIRE_AIDER_BIN", "aider")  # DEPRECATED — não tem mais efeito
OPENCODE_BIN = os.getenv("SQUIRE_OPENCODE_BIN", "opencode")
CRUSH_BIN = os.getenv("SQUIRE_CRUSH_BIN", "crush")


# ── Claude Code ────────────────────────────────────────────────────

# Claude Code é invocado via subprocess na VM
CLAUDE_CODE_BIN = os.getenv("SQUIRE_CLAUDE_BIN", "claude")

# Rate limiting
CLAUDE_CODE_MAX_CALLS_PER_WINDOW = int(os.getenv("SQUIRE_CC_MAX_CALLS", "10"))
CLAUDE_CODE_WINDOW_MINUTES = int(os.getenv("SQUIRE_CC_WINDOW_MIN", "30"))

# Rodadas máximas por task (cada rodada = inner loop até 10 + 1 homologação)
MAX_HOMOLOGATION_ATTEMPTS = int(os.getenv("SQUIRE_MAX_HOMOLOG", "5"))

# Quantas rejeições consecutivas com o mesmo padrão de erro disparam escalação imediata
LOOP_DETECT_THRESHOLD = int(os.getenv("SQUIRE_LOOP_DETECT", "3"))

# Quantos ciclos consecutivos sem nenhum arquivo modificado disparam escalação
NO_PROGRESS_THRESHOLD = int(os.getenv("SQUIRE_NO_PROGRESS", "3"))


# ── Budget / Cost ─────────────────────────────────────────────────

# Orçamento USD diário para chamadas ao Claude Code (0 = sem limite).
# Aplicado pelo RateLimiter.can_afford(): com budget esgotado, squire pausa.
# Precedência: env var > budget.json > 0 (sem limite)
DAILY_USD_BUDGET = float(os.getenv(
    "SQUIRE_DAILY_USD_BUDGET", str(_budget.get("daily_usd", 0))
))

# Limite default de USD por task (0 = sem limite). Cada Task pode sobrescrever
# via Task.max_usd. Excedido → task pausa e gera alerta.
PER_TASK_USD_CAP = float(os.getenv(
    "SQUIRE_PER_TASK_USD_CAP", str(_budget.get("per_task_usd", 0))
))

# Custo estimado de uma chamada quando ainda não sabemos o custo real
# (usado por can_afford() ANTES da chamada para reservar headroom no budget).
ESTIMATED_CALL_COST_USD = float(os.getenv("SQUIRE_ESTIMATED_CALL_USD", "0.05"))

# Tabela de preços por modelo: (USD/1M input tokens, USD/1M output tokens).
# Valores aproximados da política pública da Anthropic em 2026-Q1.
# Modelos locais (LiteLLM/Qwen) custam zero. Para sobrescrever um preço,
# edite o dict abaixo — não há env var por modelo (UX ruim).
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    # Família Claude 4
    "claude-opus-4-7":     (15.0, 75.0),
    "claude-opus-4-6":     (15.0, 75.0),
    "claude-sonnet-4-6":   (3.0,  15.0),
    "claude-sonnet-4-5":   (3.0,  15.0),
    "claude-haiku-4-5":    (1.0,  5.0),
    # Local
    "journal-synth":       (0.0,  0.0),
}


def price_for_model(model: str) -> tuple[float, float]:
    """Retorna (USD/1M input, USD/1M output) para o modelo.

    Tenta match exato; depois prefix match (cobre IDs com sufixo como
    'claude-opus-4-7[1m]'). Retorna (0, 0) se desconhecido.
    """
    if not model:
        return (0.0, 0.0)
    if model in MODEL_PRICING_PER_1M:
        return MODEL_PRICING_PER_1M[model]
    for known, price in MODEL_PRICING_PER_1M.items():
        if model.startswith(known):
            return price
    return (0.0, 0.0)


def compute_cost_usd(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Custo de uma chamada baseado em tokens reportados + tabela de preços."""
    in_price, out_price = price_for_model(model)
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


# ── Session ────────────────────────────────────────────────────────

SESSION_LOCK_TTL_MINUTES = int(os.getenv("SQUIRE_LOCK_TTL", "60"))
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("SQUIRE_HEARTBEAT", "300"))  # 5 min


# ── Helpers ────────────────────────────────────────────────────────

def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def ensure_dirs():
    """Cria estrutura de diretórios se não existir."""
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
