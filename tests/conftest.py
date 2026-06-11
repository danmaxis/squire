"""
Bootstrap de ambiente para a suíte de testes.

Roda no import (antes dos módulos de teste importarem `config`, que
congela STATE_ROOT e paths derivados em import-time): aponta o estado
para um diretório temporário, garantindo que `pytest` sem env nunca
toque o estado real em /home/ai-debian/squire-state.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "SQUIRE_STATE_ROOT", tempfile.mkdtemp(prefix="squire-test-state-")
)
