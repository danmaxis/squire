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

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import config
from backends import CodingBackend, create_backend
from models import LLMContextSummary, Task


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
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        lines = [l for l in text.splitlines() if l.strip()][:max_lines]
        for i, line in enumerate(lines):
            prefix = f"┊{arrow}" if i == 0 else "┊ "
            print(f"[{ts}]   {prefix} {line[:120]}")

    def execute(
        self,
        task: Task,
        previous_context: LLMContextSummary | None = None,
        extra_instructions: str = "",
    ) -> InnerLoopResult:
        """
        Uma iteração completa:
        1. Monta instrução com contexto da task + erros anteriores
        2. Delega execução ao backend
        3. Roda testes
        4. Retorna resultado estruturado
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
            },
        )

        if backend_result.error:
            return InnerLoopResult(error=backend_result.error)

        self._vlog("←", backend_result.raw_output)

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
        # TypeScript
        if (self.project_path / "tsconfig.json").exists():
            try:
                proc = subprocess.run(
                    ["npx", "--no", "tsc", "--noEmit"],
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
                pass  # tsc não instalado — não penalizar

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
            cmd = ["npm", "test", "--", "--watchAll=false", "--passWithNoTests"]
        elif (self.project_path / "package.json").exists() and not self._has_npm_test_script():
            result["success"] = True
            result["skipped"] = True
            result["output"] = "No test script in package.json, skipping."
            return result
        elif (self.project_path / "pyproject.toml").exists():
            cmd = ["python", "-m", "pytest", "--tb=short", "-q"]
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
