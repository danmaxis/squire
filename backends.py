"""
Backends de coding agent para o inner loop.

Cada backend recebe uma instrução em texto e retorna quais arquivos foram
modificados + output bruto. O InnerLoop é responsável por rodar os testes
após a execução — isso não é responsabilidade do backend.

Backends disponíveis:
- litellm  : LLM local via HTTP (LiteLLM / llama.cpp)
- aider    : CLI aider com --no-auto-commits
- opencode : CLI opencode
"""

from __future__ import annotations

import fcntl
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import httpx

import config

# ── LLM global lock ────────────────────────────────────────────────
# Lock de arquivo para garantir que apenas um processo chama o llama.cpp
# por vez. Evita saturação de CPU quando múltiplas ferramentas rodam juntas
# (ex: orchestrator + aider + opencode simultâneos).
_LLM_LOCK_PATH = Path(config.STATE_ROOT) / "llm.lock"


class _LLMLock:
    """Context manager que adquire um flock exclusivo antes de chamar o LLM."""

    def __init__(self, path: Path = _LLM_LOCK_PATH):
        self.path = path
        self._fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w")
        # Bloqueia até obter o lock exclusivo (chamadas simultâneas esperam)
        fcntl.flock(self._fh, fcntl.LOCK_EX)
        self._fh.write(str(time.time()))
        self._fh.flush()
        return self

    def __exit__(self, *_):
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


@dataclass
class BackendResult:
    """Resultado padronizado de um backend de execução."""
    files_touched: list[str] = field(default_factory=list)
    raw_output: str = ""          # stdout+stderr do processo/resposta
    error: str | None = None      # erro fatal (não de teste)


class CodingBackend(ABC):
    """Interface que todos os backends devem implementar."""

    @abstractmethod
    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
    ) -> BackendResult:
        """
        Executa uma instrução de codificação no projeto.

        Args:
            instruction: Texto completo da instrução para o LLM/tool
            project_path: Caminho absoluto para o projeto
            timeout: Timeout em segundos

        Returns:
            BackendResult com arquivos modificados e output
        """
        ...


# ── LiteLLM Backend ────────────────────────────────────────────────

class LiteLLMBackend(CodingBackend):
    """
    Backend que chama o LLM local via API HTTP (LiteLLM / llama.cpp).
    Faz o parse da resposta em texto livre para extrair os arquivos.
    """

    def __init__(
        self,
        base_url: str = config.LITELLM_BASE_URL,
        model: str = config.LITELLM_MODEL,
        api_key: str = config.LITELLM_API_KEY,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
    ) -> BackendResult:
        """Chama o LLM, parseia a resposta e escreve os arquivos."""
        with _LLMLock():
            client = httpx.Client(timeout=timeout)
            try:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Você é um desenvolvedor experiente. "
                                    "Implemente o que foi pedido de forma limpa e testável. "
                                    "Retorne código completo dos arquivos, não patches parciais."
                                ),
                            },
                            {"role": "user", "content": instruction},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 8192,
                    },
                )
                response.raise_for_status()
                data = response.json()
                llm_text = data["choices"][0]["message"]["content"]
            except Exception as e:
                return BackendResult(error=f"LLM call failed: {e}")
            finally:
                client.close()

        files_touched = self._apply_changes(llm_text, project_path)
        return BackendResult(files_touched=files_touched, raw_output=llm_text)

    def _apply_changes(self, llm_response: str, project_path: Path) -> list[str]:
        """
        Parseia a resposta do LLM e escreve os arquivos no projeto.

        Suporta três formatos:
        1. ```filepath:src/foo.ts   (identificador com prefixo)
        2. ```typescript            (linguagem genérica — ignorada sem caminho)
        3. src/foo.ts               (caminho na linha ANTES do fence)
           ```typescript
        """
        files_touched = []
        current_file = None
        current_content: list[str] = []
        pending_path: str | None = None

        for line in llm_response.split("\n"):
            stripped = line.strip()

            if stripped.startswith("```") and stripped != "```":
                fence_id = stripped[3:].strip()
                detected_path = self._extract_filepath(fence_id) or pending_path

                if detected_path:
                    if current_file:
                        self._write_file(project_path, current_file, "\n".join(current_content))
                        files_touched.append(current_file)
                    current_file = detected_path
                    current_content = []
                elif current_file:
                    current_content.append(line)
                pending_path = None

            elif stripped == "```":
                if current_file:
                    # fence de fechamento
                    self._write_file(project_path, current_file, "\n".join(current_content))
                    files_touched.append(current_file)
                    current_file = None
                    current_content = []
                    pending_path = None
                elif pending_path:
                    # fence de abertura sem linguagem (ex: Dockerfile\n```)
                    current_file = pending_path
                    current_content = []
                    pending_path = None

            elif current_file:
                current_content.append(line)
                pending_path = None

            else:
                pending_path = self._extract_filepath(stripped) if stripped else None

        return files_touched

    def _extract_filepath(self, fence_id: str) -> str | None:
        """
        Extrai o caminho de arquivo de um identificador de fence markdown.

        Aceita:
        - ``filepath:src/foo.ts``      → "src/foo.ts"
        - ``typescript:src/foo.ts``    → "src/foo.ts"  (linguagem:caminho)
        - ``src/foo.ts``               → "src/foo.ts"  (caminho direto com extensão)
        - ``src/foo.ts:``              → "src/foo.ts"  (dois-pontos trailing — padrão Qwen)
        - ``Dockerfile``               → "Dockerfile"  (sem extensão, sem barra)
        - ``.dockerignore``            → ".dockerignore" (começa com ponto)
        """
        if not fence_id:
            return None

        # Remove dois-pontos trailing e espaços (ex: "src/foo.ts:" → "src/foo.ts")
        candidate = fence_id.rstrip(": \t")
        if not candidate:
            return None

        if ":" in candidate:
            after_colon = candidate.split(":", 1)[1].strip()
            if after_colon and ("/" in after_colon or "." in after_colon):
                return after_colon.rstrip(": \t")

        # Caminho com barra ou extensão
        if "/" in candidate or "." in candidate:
            return candidate

        # Arquivos conhecidos sem extensão nem barra (Dockerfile, Makefile, etc.)
        _NO_EXT_FILES = {"dockerfile", "makefile", "procfile", "gemfile", "rakefile",
                         "vagrantfile", "jenkinsfile", "brewfile"}
        if candidate.lower() in _NO_EXT_FILES:
            return candidate

        return None

    def _write_file(self, project_path: Path, relative_path: str, content: str) -> None:
        """Escreve arquivo no projeto, criando diretórios se necessário."""
        full_path = project_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")


# ── Aider Backend ──────────────────────────────────────────────────

class AiderBackend(CodingBackend):
    """
    Backend que usa o CLI do aider para implementação.

    Aider acessa o filesystem e git diretamente — não precisamos parsear
    output. Arquivos modificados são detectados via `git diff --name-only`.

    Flags usadas:
    - --message: instrução em texto
    - --no-auto-commits: crítico — não commitamos aqui, o orquestrador decide
    - --yes: aceita confirmações automáticas (modo não-interativo)
    """

    def __init__(self, aider_bin: str = config.AIDER_BIN):
        self.aider_bin = aider_bin

    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
    ) -> BackendResult:
        cmd = [
            self.aider_bin,
            "--message", instruction,
            "--no-auto-commits",
            "--yes",
        ]
        with _LLMLock():
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(project_path),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                raw_output = proc.stdout + proc.stderr
                if proc.returncode != 0 and not proc.stdout.strip():
                    return BackendResult(
                        raw_output=raw_output,
                        error=f"aider exited {proc.returncode}: {proc.stderr[:300]}",
                    )
            except FileNotFoundError:
                return BackendResult(error=f"aider not found: {self.aider_bin}")
            except subprocess.TimeoutExpired:
                return BackendResult(error=f"aider timed out ({timeout}s)")

        files_touched = self._git_diff_files(project_path)
        return BackendResult(files_touched=files_touched, raw_output=raw_output)

    def _git_diff_files(self, project_path: Path) -> list[str]:
        """Lista arquivos modificados/criados desde o último commit via git diff."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            files = [f.strip() for f in proc.stdout.splitlines() if f.strip()]

            # Inclui também arquivos novos (untracked que o aider criou)
            proc2 = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            new_files = [f.strip() for f in proc2.stdout.splitlines() if f.strip()]

            return list(dict.fromkeys(files + new_files))  # preserva ordem, deduplica
        except Exception:
            return []


# ── OpenCode Backend ───────────────────────────────────────────────

class OpenCodeBackend(CodingBackend):
    """
    Backend que usa o CLI do opencode para implementação.

    OpenCode gerencia o contexto e aplica mudanças diretamente no filesystem.
    Variáveis de API (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.) devem estar
    no ambiente — são herdadas pelo subprocess.

    Arquivos modificados detectados via git diff, igual ao AiderBackend.
    """

    def __init__(self, opencode_bin: str = config.OPENCODE_BIN):
        self.opencode_bin = opencode_bin

    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
    ) -> BackendResult:
        cmd = [self.opencode_bin, "run", "--", instruction]
        with _LLMLock():
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(project_path),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                raw_output = proc.stdout + proc.stderr
                if proc.returncode != 0 and not proc.stdout.strip():
                    return BackendResult(
                        raw_output=raw_output,
                        error=f"opencode exited {proc.returncode}: {proc.stderr[:300]}",
                    )
            except FileNotFoundError:
                return BackendResult(error=f"opencode not found: {self.opencode_bin}")
            except subprocess.TimeoutExpired:
                return BackendResult(error=f"opencode timed out ({timeout}s)")

        files_touched = self._git_diff_files(project_path)
        return BackendResult(files_touched=files_touched, raw_output=raw_output)

    def _git_diff_files(self, project_path: Path) -> list[str]:
        """Mesmo mecanismo do AiderBackend."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            files = [f.strip() for f in proc.stdout.splitlines() if f.strip()]
            proc2 = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            new_files = [f.strip() for f in proc2.stdout.splitlines() if f.strip()]
            return list(dict.fromkeys(files + new_files))
        except Exception:
            return []


# ── Factory ────────────────────────────────────────────────────────

def create_backend(name: str, **kwargs) -> CodingBackend:
    """
    Instancia o backend pelo nome.

    Args:
        name: "litellm" | "aider" | "opencode"
        **kwargs: argumentos opcionais repassados ao construtor do backend

    Returns:
        Instância do backend correspondente

    Raises:
        ValueError: se o nome não for reconhecido
    """
    name = name.lower().strip()
    if name == "litellm":
        return LiteLLMBackend(**kwargs)
    if name == "aider":
        return AiderBackend(**kwargs)
    if name == "opencode":
        return OpenCodeBackend(**kwargs)
    raise ValueError(
        f"Backend desconhecido: '{name}'. Use 'litellm', 'aider' ou 'opencode'."
    )
