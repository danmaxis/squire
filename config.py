"""
Configuração centralizada do orquestrador.
Todos os valores podem ser sobrescritos via variáveis de ambiente.
"""

import os
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────

# Raiz do estado persistente (volume Unraid montado na VM)
STATE_ROOT = Path(os.getenv(
    "SQUIRE_STATE_ROOT",
    "/mnt/user/data/squire"
))

PROJECTS_DIR = STATE_ROOT / "projects"
ALERTS_FILE = STATE_ROOT / "alerts.json"
STATS_FILE = STATE_ROOT / "global-stats.json"
SESSION_LOCK_FILE = STATE_ROOT / "session.lock"
RATE_FILE = STATE_ROOT / "rate.json"


# ── LLM Local (Qwen via LiteLLM) ──────────────────────────────────

LITELLM_BASE_URL = os.getenv(
    "SQUIRE_LITELLM_URL",
    "http://192.168.50.24:4000/v1"
)

LITELLM_MODEL = os.getenv(
    "SQUIRE_LITELLM_MODEL",
    "journal-synth"  # alias apontando pro Qwen3.5-35B-A3B
)

LITELLM_API_KEY = os.getenv("SQUIRE_LITELLM_KEY", "masterofpuppets")

# Limites do inner loop
INNER_LOOP_MAX_ATTEMPTS = int(os.getenv("SQUIRE_INNER_MAX_ATTEMPTS", "10"))
INNER_LOOP_TIMEOUT_SECONDS = int(os.getenv("SQUIRE_INNER_TIMEOUT", "1200"))

# Backend de coding agent (litellm | aider | opencode)
CODING_BACKEND = os.getenv("SQUIRE_CODING_BACKEND", "litellm")
AIDER_BIN = os.getenv("SQUIRE_AIDER_BIN", "aider")
OPENCODE_BIN = os.getenv("SQUIRE_OPENCODE_BIN", "opencode")


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
