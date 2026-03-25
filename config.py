"""
Configuração centralizada do orquestrador.
Todos os valores podem ser sobrescritos via variáveis de ambiente.
"""

import os
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────

# Raiz do estado persistente (volume Unraid montado na VM)
STATE_ROOT = Path(os.getenv(
    "ORCH_STATE_ROOT",
    "/mnt/user/data/orchestrator"
))

PROJECTS_DIR = STATE_ROOT / "projects"
ALERTS_FILE = STATE_ROOT / "alerts.json"
STATS_FILE = STATE_ROOT / "global-stats.json"
SESSION_LOCK_FILE = STATE_ROOT / "session.lock"
RATE_FILE = STATE_ROOT / "rate.json"


# ── LLM Local (Qwen via LiteLLM) ──────────────────────────────────

LITELLM_BASE_URL = os.getenv(
    "ORCH_LITELLM_URL",
    "http://192.168.50.24:4000/v1"
)

LITELLM_MODEL = os.getenv(
    "ORCH_LITELLM_MODEL",
    "journal-synth"  # alias apontando pro Qwen3.5-35B-A3B
)

LITELLM_API_KEY = os.getenv("ORCH_LITELLM_KEY", "masterofpuppets")

# Limites do inner loop
INNER_LOOP_MAX_ATTEMPTS = int(os.getenv("ORCH_INNER_MAX_ATTEMPTS", "10"))
INNER_LOOP_TIMEOUT_SECONDS = int(os.getenv("ORCH_INNER_TIMEOUT", "600"))


# ── Claude Code ────────────────────────────────────────────────────

# Claude Code é invocado via subprocess na VM
CLAUDE_CODE_BIN = os.getenv("ORCH_CLAUDE_BIN", "claude")

# Rate limiting
CLAUDE_CODE_MAX_CALLS_PER_WINDOW = int(os.getenv("ORCH_CC_MAX_CALLS", "10"))
CLAUDE_CODE_WINDOW_MINUTES = int(os.getenv("ORCH_CC_WINDOW_MIN", "30"))

# Homologação
MAX_HOMOLOGATION_ATTEMPTS = int(os.getenv("ORCH_MAX_HOMOLOG", "3"))


# ── Session ────────────────────────────────────────────────────────

SESSION_LOCK_TTL_MINUTES = int(os.getenv("ORCH_LOCK_TTL", "60"))
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("ORCH_HEARTBEAT", "300"))  # 5 min


# ── Helpers ────────────────────────────────────────────────────────

def project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def ensure_dirs():
    """Cria estrutura de diretórios se não existir."""
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
