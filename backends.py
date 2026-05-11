"""
Backends de coding agent para o inner loop.

Cada backend recebe uma instrução em texto e retorna quais arquivos foram
modificados + output bruto. O InnerLoop é responsável por rodar os testes
após a execução — isso não é responsabilidade do backend.

Backends disponíveis:
- litellm  : LLM local via HTTP (LiteLLM / llama.cpp)
- aider    : CLI aider com --no-auto-commits (DESCONTINUADO)
- opencode : CLI opencode (com roteamento de agentes especialistas)
- crush    : CLI crush (sem roteamento de agentes)
"""

from __future__ import annotations

import fcntl
import re
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

import config
from models import TokenUsage

# System prompt padrão para o LiteLLM — contexto de CI automatizado
_DEFAULT_SYSTEM_PROMPT = (
    "Você é um desenvolvedor experiente num loop de CI automatizado. "
    "O código que você escrever será compilado e testado imediatamente. "
    "Retorne arquivos completos usando o formato ```filepath:caminho/arquivo.ext "
    "(sem texto fora dos blocos de código, sem TODOs, sem esqueletos). "
    "Implemente funcionalidade completa e funcional."
)

# Delays para retry em falhas de rede (segundos)
_HTTP_RETRY_DELAYS = [5, 10, 20]

# Diretórios e extensões ignorados ao detectar arquivos tocados via git ls-files.
# Previne que node_modules, dist etc. sejam incluídos no files_touched e
# consequentemente enviados como conteúdo no prompt de homologação.
_IGNORED_TREE_DIRS = frozenset({
    "node_modules", "dist", "build", ".next", ".nuxt",
    "__pycache__", ".venv", "venv", ".cache", ".tox",
    "target",  # Rust/Java
    "vendor",  # Go/PHP
})
_SOURCE_EXTENSIONS = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".go", ".rs", ".java", ".kt", ".swift",
    ".json", ".yaml", ".yml", ".toml", ".env",
    ".html", ".css", ".scss",
    ".sh", ".bash",
    ".md", ".txt",
})
_SOURCE_NAMES = frozenset({"Dockerfile", "Makefile", ".gitignore", ".env.example", "go.sum"})


def _is_source_file(rel_path: str) -> bool:
    """Retorna True se o caminho relativo é um arquivo de código/config relevante."""
    p = Path(rel_path)
    if any(part in _IGNORED_TREE_DIRS for part in p.parts):
        return False
    return p.suffix in _SOURCE_EXTENSIONS or p.name in _SOURCE_NAMES

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
    reasoning: str = ""           # chain-of-thought do modelo (se disponível)
    agent_used: str = ""          # agente opencode selecionado (vazio para outros backends)
    # Uso de tokens / custo. None ou tokens_unknown=True quando o backend
    # não expõe contadores (CLIs como opencode/crush).
    usage: Optional[TokenUsage] = None


class CodingBackend(ABC):
    """Interface que todos os backends devem implementar."""

    @abstractmethod
    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
        task_hint: dict | None = None,
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
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.system_prompt = system_prompt

    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
        task_hint: dict | None = None,
    ) -> BackendResult:
        """Chama o LLM, parseia a resposta e escreve os arquivos."""
        with _LLMLock():
            try:
                data = self._call_api_with_retry(instruction, timeout)
                message = data["choices"][0]["message"]
                llm_text = message.get("content") or ""
                # Qwen3 com --reasoning-budget retorna chain-of-thought separado
                reasoning = message.get("reasoning_content") or ""
            except Exception as e:
                return BackendResult(error=f"LLM call failed: {e}")

        files_touched = self._apply_changes(llm_text, project_path)
        usage = self._extract_usage(data)
        return BackendResult(
            files_touched=files_touched,
            raw_output=llm_text,
            reasoning=reasoning,
            usage=usage,
        )

    def _extract_usage(self, data: dict) -> TokenUsage:
        """Lê `usage` da resposta OpenAI-compatible e converte para TokenUsage.

        Se a resposta não tiver `usage` (alguns gateways locais omitem),
        sinaliza tokens_unknown=True para que o dashboard saiba que o
        custo registrado é otimista.
        """
        usage_data = data.get("usage") or {}
        pt = int(usage_data.get("prompt_tokens", 0) or 0)
        ct = int(usage_data.get("completion_tokens", 0) or 0)
        if pt == 0 and ct == 0:
            return TokenUsage(model=self.model, tokens_unknown=True)
        return TokenUsage(
            prompt_tokens=pt,
            completion_tokens=ct,
            model=self.model,
            cost_usd=config.compute_cost_usd(pt, ct, self.model),
        )

    def _call_api_with_retry(self, instruction: str, timeout: int) -> dict:
        """
        Chama a API com retry automático em falhas de rede/servidor.

        Retry em: ConnectionError, RemoteProtocolError, HTTP 5xx.
        Falha imediata em: HTTP 4xx, timeout do modelo.
        """
        last_exc: Exception | None = None
        delays = [0] + _HTTP_RETRY_DELAYS

        for attempt, delay in enumerate(delays):
            if delay:
                time.sleep(delay)
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
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": instruction},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 32768,
                    },
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code < 500:
                    raise  # 4xx: problema no request, não retry
                last_exc = e
            except (httpx.ConnectError, httpx.RemoteProtocolError,
                    httpx.ReadError, httpx.WriteError) as e:
                last_exc = e
            finally:
                client.close()

        raise RuntimeError(f"LLM API falhou após {len(_HTTP_RETRY_DELAYS)} retries: {last_exc}")

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

    def _select_agent(self, task_hint: dict) -> str:
        """
        Seleciona o agente opencode mais adequado para o contexto da task.

        Regras (em ordem de prioridade):
        1. Debug — apenas quando last_error contém marcadores de stack trace real
        2. Terminal — apenas quando o título COMEÇA com verbo operacional explícito
        3. Build — apenas para títulos que são exatamente uma tarefa de infra pura
        4. Debug — fallback quando LLM está genuinamente preso (>= 6 tentativas sem erro)
        5. Code — default seguro para qualquer implementação de feature

        Histórico: a lógica anterior de substring matching causou falsos positivos
        críticos ("check" dentro de "getCheckpoint" → terminal; "fix" + qualquer descrição
        → debug na 1ª tentativa). Ver squire_feedback_session_2026-03-29.md.
        """
        title = (task_hint.get("title") or "").lower().strip()
        last_error = task_hint.get("last_error") or ""
        attempts = task_hint.get("attempts", 0)

        # 1. Debug: só quando last_error contém marcadores de stack trace real.
        #    Contagem de falhas de teste ("0 passed, 3 failed") NÃO é suficiente.
        _STACK_MARKERS = (
            "traceback", "error:", "exception", " at ", "syntaxerror",
            "typeerror", "referenceerror", "nameerror", "assertionerror",
            "cannot find", "is not defined", "has no attribute",
        )
        if last_error and any(m in last_error.lower() for m in _STACK_MARKERS):
            return "debug"

        # 2. Terminal: só quando o título COMEÇA com verbo operacional explícito.
        #    Evita falsos positivos como "getCheckpoint" (contém "check") ou
        #    "fix database query" (contém "database").
        if re.match(r"^(run|migrate|seed|init|deploy|start|stop|restart)\b", title):
            return "terminal"

        # 3. Build: só para tarefas cujo título é exatamente uma operação de infra pura.
        _BUILD_TITLES = {
            "scaffold project", "setup project", "configure ci",
            "add dockerfile", "setup docker", "configure webpack",
            "configure vite", "init project",
        }
        if title in _BUILD_TITLES:
            return "build"

        # 4. Stuck sem erro explícito: debug apenas após muitas tentativas.
        if attempts >= 6:
            return "debug"

        # 5. Default seguro: code agent para toda implementação de feature.
        return "code"

    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
        task_hint: dict | None = None,
    ) -> BackendResult:
        agent = self._select_agent(task_hint or {})
        cmd = [self.opencode_bin, "run", "--agent", agent, "--", instruction]
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
        return BackendResult(
            files_touched=files_touched,
            raw_output=raw_output,
            agent_used=agent,
            usage=TokenUsage(tokens_unknown=True),
        )

    def _git_diff_files(self, project_path: Path) -> list[str]:
        """Mesmo mecanismo do AiderBackend (com filtro de arquivos de código)."""
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
            return [f for f in dict.fromkeys(files + new_files) if _is_source_file(f)]
        except Exception:
            return []


# ── Crush Backend ─────────────────────────────────────────────────

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")


class CrushBackend(CodingBackend):
    """
    Backend que usa o CLI crush para implementação.

    crush é similar ao opencode mas sem roteamento de agentes especialistas.
    Usa `crush run --cwd <path> --quiet --yolo <prompt>` para execução
    não-interativa. A instrução é passada via stdin para evitar limitações
    de ARG_MAX com prompts longos.

    Arquivos modificados detectados via git diff (mesmo mecanismo do OpenCodeBackend).
    """

    def __init__(self, crush_bin: str = config.CRUSH_BIN):
        self.crush_bin = crush_bin

    def execute_instruction(
        self,
        instruction: str,
        project_path: Path,
        timeout: int,
        task_hint: dict | None = None,
    ) -> BackendResult:
        cmd = [self.crush_bin, "run", "--cwd", str(project_path), "--quiet", "--yolo"]
        with _LLMLock():
            try:
                proc = subprocess.run(
                    cmd,
                    input=instruction,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                raw_output = _ANSI_ESCAPE.sub("", proc.stdout + proc.stderr)
                if proc.returncode != 0 and not proc.stdout.strip():
                    return BackendResult(
                        raw_output=raw_output,
                        error=f"crush exited {proc.returncode}: {proc.stderr[:300]}",
                    )
            except FileNotFoundError:
                return BackendResult(error=f"crush not found: {self.crush_bin}")
            except subprocess.TimeoutExpired:
                return BackendResult(error=f"crush timed out ({timeout}s)")

        files_touched = self._git_diff_files(project_path)
        return BackendResult(
            files_touched=files_touched,
            raw_output=raw_output,
            agent_used="crush",
            usage=TokenUsage(tokens_unknown=True),
        )

    def _git_diff_files(self, project_path: Path) -> list[str]:
        """Mesmo mecanismo do OpenCodeBackend."""
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
            return [f for f in dict.fromkeys(files + new_files) if _is_source_file(f)]
        except Exception:
            return []


# ── Utilitários de parse ───────────────────────────────────────────

def parse_and_apply_files(text: str, project_path: Path) -> list[str]:
    """
    Parseia output do LLM (formato ```filepath:caminho ```) e escreve os arquivos.

    Função de módulo que delega ao parser do LiteLLMBackend.
    Usada pelo TechnicalEscalation.implement_directly() e por outros callers.
    """
    return LiteLLMBackend()._apply_changes(text, project_path)


# ── Factory ────────────────────────────────────────────────────────

def create_backend(name: str, **kwargs) -> CodingBackend:
    """
    Instancia o backend pelo nome.

    Args:
        name: "litellm" | "aider" | "opencode" | "crush"
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
        raise ValueError(
            "Backend 'aider' foi descontinuado (2026-03-29). "
            "Use 'opencode' ou 'litellm'. "
            "Motivo: aider sobrescreveu tsconfig.json, criou artefatos .js e oscilou "
            "sem convergir em sessão real. Ver squire_feedback_session_2026-03-29.md."
        )
    if name == "opencode":
        return OpenCodeBackend(**kwargs)
    if name == "crush":
        return CrushBackend(**kwargs)
    raise ValueError(
        f"Backend desconhecido: '{name}'. Use 'litellm', 'opencode' ou 'crush'."
    )
