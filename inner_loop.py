"""
Inner loop — executa o ciclo de implementação com o LLM local.

Responsabilidades:
- Montar instrução de codificação
- Delegar execução ao backend (LiteLLM, Aider, OpenCode)
- Rodar testes e lint
- Reportar resultado para o orquestrador decidir próximo passo

O design é agent-agnostic: a classe InnerLoopResult padroniza o output,
e a implementação pode ser trocada via o parâmetro `backend` (string ou
instância de CodingBackend).
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import config
from backends import CodingBackend, create_backend
from models import Effort, LLMContextSummary, Task, TokenUsage


@dataclass
class InnerLoopResult:
    """Resultado padronizado de uma iteração do inner loop."""
    success: bool = False           # testes passaram?
    tests_passing: int = 0
    tests_failing: int = 0
    tests_skipped: bool = False     # sem runner configurado no projeto
    test_output: str = ""           # stdout/stderr do test runner
    lint_clean: bool = False
    files_touched: list[str] = field(default_factory=list)
    error: str | None = None        # erro fatal (não de teste)
    llm_response: str = ""          # output bruto do backend (pra debug)
    context_summary: LLMContextSummary | None = None
    usage: TokenUsage | None = None  # tokens + custo da chamada ao backend


class InnerLoop:
    """Executa uma iteração de implementação usando o backend configurado."""

    def __init__(
        self,
        project_path: str,
        backend: str | CodingBackend = config.CODING_BACKEND,
        verbose: bool = True,
    ):
        self.project_path = Path(project_path)
        self.verbose = verbose
        if isinstance(backend, str):
            self.backend = create_backend(backend)
        else:
            self.backend = backend

    def _vlog(self, arrow: str, text: str, max_lines: int = 3) -> None:
        """Imprime preview de até 3 linhas com prefixo visual ┊."""
        if not self.verbose:
            return
        from datetime import datetime, timezone
        ts = datetime.now().astimezone().strftime("%H:%M:%S")
        lines = [l for l in text.splitlines() if l.strip()][:max_lines]
        for i, line in enumerate(lines):
            prefix = f"┊{arrow}" if i == 0 else "┊ "
            print(f"[{ts}]   {prefix} {line[:120]}")

    # ── Proteção de testes (Gap 6) ─────────────────────────────────

    def snapshot_test_hashes(self) -> dict[str, str]:
        """SHA256 de todos os test_*.py — tirado após fase RED como referência."""
        return {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.project_path.rglob("test_*.py")
            if not any(part in (".venv", "venv", "__pycache__", "node_modules")
                       for part in p.parts)
        }

    def check_test_integrity(
        self,
        hashes_before: dict[str, str],
    ) -> list[str]:
        """Retorna lista de test_*.py modificados desde o snapshot."""
        hashes_after = self.snapshot_test_hashes()
        modified = []
        for path, h in hashes_before.items():
            if hashes_after.get(path) != h:
                modified.append(path)
        # Novos arquivos de teste criados pelo Executor também são suspeitos
        for path in hashes_after:
            if path not in hashes_before:
                modified.append(path)
        return modified

    def revert_test_files(self, modified: list[str]) -> None:
        """Reverte arquivos de teste modificados via git checkout."""
        for path in modified:
            try:
                rel = Path(path).relative_to(self.project_path)
                subprocess.run(
                    ["git", "checkout", "--", str(rel)],
                    cwd=str(self.project_path),
                    capture_output=True,
                )
            except Exception:
                pass

    # ── Effort routing (Gap 4) ──────────────────────────────────────

    @staticmethod
    def _model_for_effort(effort: Effort) -> str:
        return {
            Effort.low:    config.MODEL_LOW,
            Effort.medium: config.MODEL_MEDIUM,
            Effort.high:   config.MODEL_HIGH,
        }[effort]

    # ── Execução principal ──────────────────────────────────────────

    def execute(
        self,
        task: Task,
        previous_context: LLMContextSummary | None = None,
        extra_instructions: str = "",
        test_hashes: dict[str, str] | None = None,
    ) -> InnerLoopResult:
        """
        Uma iteração completa:
        1. Monta instrução com contexto da task + erros anteriores
        2. Injeta progress.txt e contexto Viking se disponíveis
        3. Delega execução ao backend (com modelo por effort)
        4. Verifica integridade dos testes (se hashes fornecidos)
        5. Roda testes e retorna resultado estruturado
        """
        instruction = self._build_instruction(task, previous_context, extra_instructions)
        self._vlog("→", instruction)

        backend_result = self.backend.execute_instruction(
            instruction=instruction,
            project_path=self.project_path,
            timeout=config.INNER_LOOP_TIMEOUT_SECONDS,
            task_hint={
                "title": task.title,
                "description": task.description,
                "attempts": task.attempts,
                "skip_homologation": task.skip_homologation,
                "last_error": previous_context.last_error if previous_context else None,
                "model": self._model_for_effort(task.effort),
            },
        )

        if backend_result.error:
            return InnerLoopResult(error=backend_result.error, usage=backend_result.usage)

        if backend_result.agent_used:
            self._vlog("◆", f"agente: {backend_result.agent_used}")
        self._vlog("←", backend_result.raw_output)

        # Verificar integridade dos arquivos de teste
        if test_hashes is not None:
            modified = self.check_test_integrity(test_hashes)
            if modified:
                rel_names = [Path(p).name for p in modified]
                self.revert_test_files(modified)
                return InnerLoopResult(
                    success=False,
                    error=(
                        f"VIOLAÇÃO: Executor modificou arquivo(s) de teste protegido(s): "
                        f"{', '.join(rel_names)}. "
                        f"Alterações revertidas via git. "
                        f"PROIBIDO modificar test_*.py — implemente apenas o código de produção."
                    ),
                    usage=backend_result.usage,
                )

        test_result = self._run_tests()

        context = LLMContextSummary(
            last_instruction=instruction[:500],
            files_touched=backend_result.files_touched,
            last_error=test_result.get("error") if not test_result["success"] else None,
            tests_passing=test_result["passing"],
            tests_failing=test_result["failing"],
            test_summary=test_result["output"][:300],
        )

        return InnerLoopResult(
            success=test_result["success"],
            tests_passing=test_result["passing"],
            tests_failing=test_result["failing"],
            tests_skipped=test_result.get("skipped", False),
            test_output=test_result["output"],
            lint_clean=test_result.get("lint_clean", True),
            files_touched=backend_result.files_touched,
            llm_response=backend_result.raw_output[:1000],
            context_summary=context,
            usage=backend_result.usage,
        )

    def _build_instruction(
        self,
        task: Task,
        previous_context: LLMContextSummary | None,
        extra_instructions: str,
    ) -> str:
        """Monta o texto de instrução para o backend."""
        parts = [
            f"## Task: {task.title}",
            f"{task.description}",
            "",
            f"Projeto em: {self.project_path}",
        ]

        if previous_context and previous_context.last_error:
            parts.extend([
                "",
                "## Erro da tentativa anterior",
                f"```\n{previous_context.last_error}\n```",
                "",
                f"Arquivos já modificados: {', '.join(previous_context.files_touched)}",
                f"Testes passando: {previous_context.tests_passing}, "
                f"falhando: {previous_context.tests_failing}",
            ])

        if task.subtasks:
            parts.extend(["", "## Subtasks"])
            for st in task.subtasks:
                marker = "x" if st.status == "completed" else " "
                parts.append(f"- [{marker}] {st.title}")

        if extra_instructions:
            parts.extend(["", "## Instruções adicionais", extra_instructions])

        # Injetar progress.txt se disponível (memória de longo prazo — padrão Ralph Loop)
        try:
            import progress as _progress
            prog_text = _progress.load_progress(str(self.project_path.name))
            if prog_text.strip():
                parts.extend(["", "## Aprendizado de iterações anteriores", prog_text[:1500]])
        except Exception:
            pass

        # Injetar contexto Viking se disponível (padrão Viking — /docs/viking/)
        try:
            import viking as _viking
            viking_ctx = _viking.load_viking_context(self.project_path)
            if viking_ctx.strip():
                parts.extend(["", "## Restrições de domínio (Padrão Viking)", viking_ctx])
        except Exception:
            pass

        # Restrições permanentes — aparecem em TODA instrução, não só após violação
        parts.extend([
            "",
            "## Restrições obrigatórias",
            "- PROIBIDO modificar qualquer arquivo test_*.py ou *_test.py",
            "- Implemente APENAS código de produção",
            "- Os testes são imutáveis — se falharem, corrija o código, nunca o teste",
        ])

        # A seção de formato só faz sentido para LiteLLM (que parseia output em texto)
        # Aider/OpenCode não precisam dela, mas não prejudica incluir
        from backends import LiteLLMBackend
        if isinstance(self.backend, LiteLLMBackend):
            parts.extend([
                "",
                "## Formato de resposta",
                "Retorne o código completo dos arquivos modificados,",
                "cada um delimitado por ```filepath:caminho/do/arquivo```.",
                "Depois explique brevemente o que mudou.",
            ])

        return "\n".join(parts)

    def _has_npm_test_script(self) -> bool:
        """Verifica se package.json tem script 'test' definido."""
        import json as _json
        try:
            pkg = _json.loads((self.project_path / "package.json").read_text())
            return "test" in pkg.get("scripts", {})
        except Exception:
            return False

    def _run_syntax_check(self) -> dict | None:
        """
        Verifica sintaxe dos arquivos ANTES de rodar os testes.

        - TypeScript: npx tsc --noEmit (se tsconfig.json existe)
        - Python: python -m py_compile em todos os .py modificados

        Retorna dict de falha (mesmo formato de _run_tests) se a sintaxe falhar,
        ou None se tudo ok (ou se não houver checker disponível).
        """
        # TypeScript — usa tsc local (node_modules/.bin/tsc) para evitar
        # que npx falhe com "canceled due to missing packages" em setups novos
        if (self.project_path / "tsconfig.json").exists():
            tsc_bin = self.project_path / "node_modules" / ".bin" / "tsc"
            if not tsc_bin.exists():
                pass  # tsc não instalado ainda — não penalizar
            else:
                try:
                    proc = subprocess.run(
                        [str(tsc_bin), "--noEmit"],
                        cwd=str(self.project_path),
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if proc.returncode != 0:
                        output = (proc.stdout + proc.stderr)[:2000]
                        return {
                            "success": False, "passing": 0, "failing": 1,
                            "output": f"[TypeScript] Erro de sintaxe:\n{output}",
                            "lint_clean": False, "skipped": False,
                        }
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass  # não penalizar se tsc falhar por razão externa

        # Python
        if (self.project_path / "pyproject.toml").exists() or list(self.project_path.glob("*.py")):
            import ast
            errors = []
            for py_file in sorted(self.project_path.rglob("*.py")):
                # Ignora .venv e __pycache__
                parts = py_file.parts
                if any(p in (".venv", "venv", "__pycache__", "node_modules") for p in parts):
                    continue
                try:
                    source = py_file.read_text(encoding="utf-8", errors="ignore")
                    ast.parse(source, filename=str(py_file))
                except SyntaxError as e:
                    rel = str(py_file.relative_to(self.project_path))
                    errors.append(f"  {rel}:{e.lineno}: {e.msg}")
            if errors:
                return {
                    "success": False, "passing": 0, "failing": len(errors),
                    "output": f"[Python] Erro(s) de sintaxe:\n" + "\n".join(errors),
                    "lint_clean": False, "skipped": False,
                }

        return None  # sintaxe ok

    def run_tests(self) -> dict:
        """API pública para rodar os testes do projeto (usada por `squire fix`)."""
        return self._run_tests()

    def _run_tests(self) -> dict:
        """
        Roda testes do projeto. Detecta o runner baseado nos arquivos presentes.

        Retorna dict com: success, passing, failing, output, lint_clean
        """
        # Verificação sintática rápida antes dos testes
        syntax_error = self._run_syntax_check()
        if syntax_error:
            return syntax_error

        result = {"success": False, "passing": 0, "failing": 0, "output": "", "lint_clean": True, "skipped": False}

        # Detectar test runner
        if (self.project_path / "package.json").exists() and self._has_npm_test_script():
            import json as _json
            try:
                _pkg = _json.loads((self.project_path / "package.json").read_text())
                _deps = {**_pkg.get("dependencies", {}), **_pkg.get("devDependencies", {})}
                _is_vitest = "vitest" in _deps
            except Exception:
                _is_vitest = False
            # --watchAll=false is jest/CRA-specific; vitest does not accept it
            _extra = ["--passWithNoTests"] if _is_vitest else ["--watchAll=false", "--passWithNoTests"]
            cmd = ["npm", "test", "--"] + _extra
        elif (self.project_path / "package.json").exists() and not self._has_npm_test_script():
            result["success"] = True
            result["skipped"] = True
            result["output"] = "No test script in package.json, skipping."
            return result
        elif (self.project_path / "pyproject.toml").exists():
            import shutil
            venv_python = self.project_path / ".venv" / "bin" / "python"
            py_bin = str(venv_python) if venv_python.exists() else (shutil.which("python3") or "python")
            cmd = [py_bin, "-m", "pytest", "--tb=short", "-q"]
        elif (self.project_path / "go.mod").exists():
            cmd = ["go", "test", "./..."]
        else:
            result["success"] = True
            result["skipped"] = True
            result["output"] = "No test runner detected, skipping."
            return result

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            result["output"] = proc.stdout + proc.stderr
            result["success"] = proc.returncode == 0

            output = result["output"]
            if "passed" in output.lower():
                import re
                passed = re.search(r"(\d+)\s+passed", output)
                failed = re.search(r"(\d+)\s+failed", output)
                result["passing"] = int(passed.group(1)) if passed else 0
                result["failing"] = int(failed.group(1)) if failed else 0
            elif "passed" in output or "failed" in output:
                import re
                passed = re.search(r"(\d+)\s+passed", output)
                failed = re.search(r"(\d+)\s+failed", output)
                result["passing"] = int(passed.group(1)) if passed else 0
                result["failing"] = int(failed.group(1)) if failed else 0

        except subprocess.TimeoutExpired:
            result["output"] = "Test execution timed out (120s)"
        except FileNotFoundError as e:
            result["output"] = f"Test runner not found: {e}"
            result["success"] = True  # não penalizar se runner não instalado

        return result
