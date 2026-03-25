"""
Inner loop — executa o ciclo de implementação com o LLM local.

Responsabilidades:
- Enviar instrução de codificação ao Qwen via LiteLLM
- Aplicar as mudanças no filesystem do projeto
- Rodar testes e lint
- Reportar resultado para o orquestrador decidir próximo passo

O design é agent-agnostic: a classe InnerLoopResult padroniza o output,
e a implementação pode ser trocada (ex: de LiteLLM direto para OpenCode
ou Aider-CE) sem mudar o orquestrador.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import httpx

import config
from models import LLMContextSummary, Task


@dataclass
class InnerLoopResult:
    """Resultado padronizado de uma iteração do inner loop."""
    success: bool = False           # testes passaram?
    tests_passing: int = 0
    tests_failing: int = 0
    test_output: str = ""           # stdout/stderr do test runner
    lint_clean: bool = False
    files_touched: list[str] = field(default_factory=list)
    error: str | None = None        # erro fatal (não de teste)
    llm_response: str = ""          # resposta bruta do LLM (pra debug)
    context_summary: LLMContextSummary | None = None


class InnerLoop:
    """Executa uma iteração de implementação usando o LLM local via LiteLLM."""

    def __init__(
        self,
        project_path: str,
        base_url: str = config.LITELLM_BASE_URL,
        model: str = config.LITELLM_MODEL,
        api_key: str = config.LITELLM_API_KEY,
    ):
        self.project_path = Path(project_path)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = httpx.Client(timeout=config.INNER_LOOP_TIMEOUT_SECONDS)

    def execute(
        self,
        task: Task,
        previous_context: LLMContextSummary | None = None,
        extra_instructions: str = "",
    ) -> InnerLoopResult:
        """
        Uma iteração completa:
        1. Monta prompt com contexto da task + erros anteriores
        2. Chama o LLM local
        3. Aplica mudanças (o LLM retorna patches/código)
        4. Roda testes
        5. Retorna resultado estruturado
        """
        # 1. Montar prompt
        prompt = self._build_prompt(task, previous_context, extra_instructions)

        # 2. Chamar LLM local
        try:
            llm_response = self._call_llm(prompt)
        except Exception as e:
            return InnerLoopResult(error=f"LLM call failed: {e}")

        # 3. Aplicar mudanças no projeto
        files_touched = self._apply_changes(llm_response)

        # 4. Rodar testes
        test_result = self._run_tests()

        # 5. Montar resultado
        context = LLMContextSummary(
            last_instruction=prompt[:500],  # truncar pra checkpoint
            files_touched=files_touched,
            last_error=test_result.get("error") if not test_result["success"] else None,
            tests_passing=test_result["passing"],
            tests_failing=test_result["failing"],
            test_summary=test_result["output"][:300],
        )

        return InnerLoopResult(
            success=test_result["success"],
            tests_passing=test_result["passing"],
            tests_failing=test_result["failing"],
            test_output=test_result["output"],
            lint_clean=test_result.get("lint_clean", True),
            files_touched=files_touched,
            llm_response=llm_response[:1000],
            context_summary=context,
        )

    def _build_prompt(
        self,
        task: Task,
        previous_context: LLMContextSummary | None,
        extra_instructions: str,
    ) -> str:
        """Monta o prompt para o LLM local com contexto da task."""
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

        parts.extend([
            "",
            "## Formato de resposta",
            "Retorne o código completo dos arquivos modificados,",
            "cada um delimitado por ```filepath:caminho/do/arquivo```.",
            "Depois explique brevemente o que mudou.",
        ])

        return "\n".join(parts)

    def _call_llm(self, prompt: str) -> str:
        """Chama o LLM local via endpoint OpenAI-compatible do LiteLLM."""
        response = self.client.post(
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
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 8192,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _apply_changes(self, llm_response: str) -> list[str]:
        """
        Parseia a resposta do LLM e escreve os arquivos no projeto.

        Espera blocos no formato:
        ```filepath:src/components/Timeline.tsx
        <conteúdo do arquivo>
        ```
        """
        files_touched = []
        current_file = None
        current_content = []

        for line in llm_response.split("\n"):
            if line.startswith("```") and not line.strip() == "```":
                fence_id = line[3:].strip()  # ex: "filepath:src/foo.ts" ou "typescript:src/foo.ts"
                detected_path = self._extract_filepath(fence_id)

                if detected_path:
                    # Início de novo arquivo
                    if current_file:
                        self._write_file(current_file, "\n".join(current_content))
                        files_touched.append(current_file)
                    current_file = detected_path
                    current_content = []
                elif current_file:
                    # Fence de abertura sem path enquanto estamos dentro de um bloco — tratar como conteúdo
                    current_content.append(line)
            elif line.strip() == "```" and current_file:
                # Fim do bloco
                self._write_file(current_file, "\n".join(current_content))
                files_touched.append(current_file)
                current_file = None
                current_content = []
            elif current_file:
                current_content.append(line)

        return files_touched

    def _extract_filepath(self, fence_id: str) -> str | None:
        """
        Extrai o caminho de arquivo de um identificador de fence markdown.

        Aceita:
        - ``filepath:src/foo.ts``  → "src/foo.ts"
        - ``typescript:src/foo.ts``  → "src/foo.ts"  (linguagem:caminho)
        - ``src/foo.ts``  → "src/foo.ts"  (caminho direto com extensão)
        """
        if not fence_id:
            return None

        # Formato "algo:caminho/com/extensao" — extrai a parte após o ":"
        if ":" in fence_id:
            after_colon = fence_id.split(":", 1)[1].strip()
            if after_colon and ("/" in after_colon or "." in after_colon):
                return after_colon

        # Formato direto: parece um caminho (tem extensão ou barra)
        if "/" in fence_id or (fence_id.count(".") >= 1 and not fence_id.startswith(".")):
            return fence_id

        return None

    def _write_file(self, relative_path: str, content: str) -> None:
        """Escreve arquivo no projeto, criando diretórios se necessário."""
        full_path = self.project_path / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    def _run_tests(self) -> dict:
        """
        Roda testes do projeto. Detecta o runner baseado nos arquivos presentes.

        Retorna dict com: success, passing, failing, output, lint_clean
        """
        result = {"success": False, "passing": 0, "failing": 0, "output": "", "lint_clean": True}

        # Detectar test runner
        if (self.project_path / "package.json").exists():
            cmd = ["npm", "test", "--", "--watchAll=false", "--passWithNoTests"]
        elif (self.project_path / "pyproject.toml").exists():
            cmd = ["python", "-m", "pytest", "--tb=short", "-q"]
        elif (self.project_path / "go.mod").exists():
            cmd = ["go", "test", "./..."]
        else:
            # Sem runner detectado — considera sucesso (projeto ainda não tem testes)
            result["success"] = True
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

            # Parse básico de contagem (heurística, varia por runner)
            output = result["output"]
            if "passed" in output.lower():
                # Jest/Vitest style: "Tests: 3 passed, 1 failed"
                import re
                passed = re.search(r"(\d+)\s+passed", output)
                failed = re.search(r"(\d+)\s+failed", output)
                result["passing"] = int(passed.group(1)) if passed else 0
                result["failing"] = int(failed.group(1)) if failed else 0
            elif "passed" in output or "failed" in output:
                # pytest style: "4 passed, 1 failed"
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
