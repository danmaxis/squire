"""
Homologador — interface com Claude Code para review de alto nível.

O Claude Code é invocado via subprocess (--print mode) para fazer
uma avaliação de qualidade do código produzido pelo LLM local.

A homologação não é técnica (isso o inner loop já fez via testes),
mas de engenharia: o código faz sentido? Segue os padrões do projeto?
Tem edge cases não cobertos? É legível e manutenível?
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import config
from models import LLMContextSummary, Task


@dataclass
class HomologationResult:
    """Resultado da homologação pelo Claude Code."""
    approved: bool = False
    feedback: str = ""           # razão da aprovação/rejeição
    suggestions: list[str] = None  # melhorias sugeridas (mesmo se aprovado)
    error: str | None = None     # erro de execução (não de review)

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class Homologator:
    """Invoca o Claude Code para homologar código do LLM local."""

    def __init__(
        self,
        project_path: str,
        claude_bin: str = config.CLAUDE_CODE_BIN,
    ):
        self.project_path = Path(project_path)
        self.claude_bin = claude_bin

    def review(
        self,
        task: Task,
        context: LLMContextSummary,
        attempt: int = 1,
    ) -> HomologationResult:
        """
        Solicita ao Claude Code uma revisão do trabalho feito na task.

        Usa o modo --print para interação não-interativa:
        envia o prompt e recebe a resposta como stdout.
        """
        prompt = self._build_review_prompt(task, context, attempt)

        try:
            result = subprocess.run(
                [
                    self.claude_bin,
                    "--print",      # modo não-interativo
                    "--output-format", "json",
                    prompt,
                ],
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=180,  # 3 min max para review
            )

            if result.returncode != 0:
                return HomologationResult(
                    error=f"Claude Code exited with code {result.returncode}: "
                          f"{result.stderr[:500]}",
                )

            if not result.stdout.strip():
                # stdout vazio com returncode 0 — stderr pode ter info
                stderr_hint = result.stderr[:200] if result.stderr else "sem stderr"
                return HomologationResult(
                    error=f"Claude Code retornou stdout vazio (stderr: {stderr_hint})",
                )

            return self._parse_response(result.stdout)

        except subprocess.TimeoutExpired:
            return HomologationResult(
                error="Claude Code review timed out (180s)",
            )
        except FileNotFoundError:
            return HomologationResult(
                error=f"Claude Code binary not found: {self.claude_bin}",
            )

    def _build_review_prompt(
        self,
        task: Task,
        context: LLMContextSummary,
        attempt: int,
    ) -> str:
        """Monta o prompt de homologação para o Claude Code."""
        # Incluir conteúdo dos arquivos tocados (máx 200 linhas por arquivo)
        files_section = self._read_files_for_review(context.files_touched)

        previous_section = ""
        if attempt > 1:
            previous_section = (
                f"\n\nEsta é a tentativa #{attempt} de homologação. "
                "Nas anteriores, os seguintes problemas foram apontados. "
                "Verifique se foram resolvidos."
            )

        return f"""Você está fazendo homologação de código como um tech lead.

## Contexto
Task: {task.title}
Descrição: {task.description}
Tentativa de homologação: {attempt} de {task.max_homologation_attempts}
Testes: {context.tests_passing} passando, {context.tests_failing} falhando
{files_section}
{previous_section}

## O que avaliar
1. O código resolve o que a task pede? (verifique se os arquivos EXIGIDOS pela descrição foram criados)
2. Há edge cases não cobertos pelos testes?
3. O código é legível e segue boas práticas?
4. Tem problemas de segurança ou performance óbvios?

## Formato de resposta (JSON estrito)
Responda APENAS com JSON válido, sem markdown:
{{
  "approved": true/false,
  "feedback": "Explicação da decisão",
  "suggestions": ["melhoria 1", "melhoria 2"]
}}"""

    def _read_files_for_review(self, files_touched: list[str]) -> str:
        """Lê o conteúdo dos arquivos modificados para incluir no prompt."""
        if not files_touched:
            return "\n\nNenhum arquivo foi modificado/criado nesta tentativa."

        parts = ["\n\nArquivos modificados:"]
        for rel_path in files_touched:
            full_path = self.project_path / rel_path
            try:
                lines = full_path.read_text(encoding="utf-8").splitlines()
                content = "\n".join(lines[:200])
                if len(lines) > 200:
                    content += f"\n... (truncado — {len(lines)} linhas no total)"
                parts.append(f"\n### {rel_path}\n```\n{content}\n```")
            except Exception as e:
                parts.append(f"\n### {rel_path}\n(erro ao ler: {e})")

        return "\n".join(parts)

    def _parse_response(self, stdout: str) -> HomologationResult:
        """Parseia a resposta do Claude Code."""
        try:
            # Claude Code com --output-format json retorna estruturado
            data = json.loads(stdout)

            # Se o Claude Code retornou no formato de mensagem
            if "result" in data:
                content = data["result"]
            elif "content" in data:
                content = data["content"]
            else:
                content = stdout

            # Tentar parsear o JSON de review dentro da resposta
            if isinstance(content, str):
                # Limpar possíveis markdown fences
                clean = content.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[1]
                    clean = clean.rsplit("```", 1)[0]
                review = json.loads(clean)
            elif isinstance(content, dict):
                review = content
            else:
                return HomologationResult(
                    error=f"Unexpected response format: {type(content)}",
                )

            return HomologationResult(
                approved=review.get("approved", False),
                feedback=review.get("feedback", ""),
                suggestions=review.get("suggestions", []),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Se não conseguiu parsear, trata como aprovação condicional
            # com o texto bruto como feedback
            return HomologationResult(
                approved=False,
                feedback=f"Não foi possível parsear a resposta: {stdout[:500]}",
                error=f"Parse error: {e}",
            )


class TechnicalEscalation:
    """
    Escalação técnica — quando o LLM local empaca, pede ajuda
    ao Claude Code para desbloquear (não homologação, mas debugging).

    Uso mais caro de tokens — só chamado quando inner loop esgota tentativas.
    """

    def __init__(
        self,
        project_path: str,
        claude_bin: str = config.CLAUDE_CODE_BIN,
    ):
        self.project_path = Path(project_path)
        self.claude_bin = claude_bin

    def unblock(
        self,
        task: Task,
        context: LLMContextSummary,
    ) -> str:
        """
        Pede ao Claude Code para analisar o erro e sugerir um caminho.
        Retorna instruções que serão passadas de volta ao LLM local.
        """
        prompt = f"""O LLM local está empacado nesta task após múltiplas tentativas.

Task: {task.title}
Descrição: {task.description}
Último erro: {context.last_error}
Arquivos tocados: {', '.join(context.files_touched)}
Testes: {context.tests_passing} passando, {context.tests_failing} falhando
Resumo dos testes: {context.test_summary}

Analise o problema e forneça instruções claras e específicas para o
LLM local resolver. Seja direto — ele vai receber exatamente o que
você escrever como contexto adicional na próxima tentativa."""

        try:
            result = subprocess.run(
                [self.claude_bin, "--print", prompt],
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""
