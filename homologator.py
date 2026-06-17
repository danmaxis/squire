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
from typing import Optional

import config
import viking as _viking
from models import LLMContextSummary, Task, TokenUsage


def _extract_usage_from_claude_json(data: dict) -> Optional[TokenUsage]:
    """Lê custo + tokens da resposta `claude --print --output-format json`.

    O wrapper Claude Code expõe os campos no nível raiz do JSON:
    `total_cost_usd`, `model`, e `usage.{input_tokens, output_tokens, cache_read_input_tokens}`.
    Retorna None quando nenhum desses campos está presente — caller decide se
    isso é um erro ou apenas um output não-JSON.
    """
    if not isinstance(data, dict):
        return None
    has_cost = "total_cost_usd" in data
    has_usage = isinstance(data.get("usage"), dict)
    if not (has_cost or has_usage):
        return None
    usage = data.get("usage") or {}
    pt = int(usage.get("input_tokens", 0) or 0)
    ct = int(usage.get("output_tokens", 0) or 0)
    cached = int(usage.get("cache_read_input_tokens", 0) or 0)
    model = data.get("model", "") or ""
    # Versões recentes do claude --print não trazem "model" no topo, só as
    # chaves de "modelUsage" — sem isto o cost_by_model fica vazio para sempre
    if not model:
        model_usage = data.get("modelUsage")
        if isinstance(model_usage, dict) and model_usage:
            model = next(iter(model_usage))
    cost = float(data.get("total_cost_usd", 0.0) or 0.0)
    # Fallback: se Claude não reportou custo mas reportou tokens, computa da tabela
    if cost == 0.0 and (pt or ct) and model:
        cost = config.compute_cost_usd(pt, ct, model)
    return TokenUsage(
        prompt_tokens=pt,
        completion_tokens=ct,
        cached_tokens=cached,
        cost_usd=cost,
        model=model,
        tokens_unknown=(pt == 0 and ct == 0 and cost == 0.0),
    )


def _extract_json_object(text: str) -> Optional[dict]:
    """Extrai o primeiro objeto JSON válido embutido em texto livre.

    Tenta raw_decode a partir de cada '{' — cobre respostas em que o
    modelo envolve o JSON do veredito em prosa.
    """
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


@dataclass
class HomologationResult:
    """Resultado da homologação pelo Claude Code."""
    approved: bool = False
    summary: str = ""            # resumo em até 3 linhas — para log e contexto do agente local
    feedback: str = ""           # explicação detalhada da decisão
    fix_suggestion: str = ""     # passos concretos para o agente local corrigir (rejeição)
    suggestions: list[str] = None  # melhorias sugeridas (mesmo se aprovado)
    error: str | None = None     # erro de execução (não de review)
    # Classificação do erro: "infra" = transiente (parse/timeout/stdout vazio —
    # vale retry), "config" = não se resolve sozinho (binário ausente), None = sem erro
    error_kind: str | None = None
    usage: Optional[TokenUsage] = None  # tokens + custo reportados pelo Claude Code

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class Homologator:
    """Invoca o Claude Code para homologar código do LLM local."""

    def __init__(
        self,
        project_path: str,
        claude_bin: str = config.CLAUDE_CODE_BIN,
        verbose: bool = True,
    ):
        self.project_path = Path(project_path)
        self.claude_bin = claude_bin
        self.verbose = verbose

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

    def review(
        self,
        task: Task,
        context: LLMContextSummary,
        attempt: int = 1,
        test_hashes: dict[str, str] | None = None,
    ) -> HomologationResult:
        """
        Solicita ao Claude Code uma revisão do trabalho feito na task.

        Usa o modo --print para interação não-interativa:
        envia o prompt e recebe a resposta como stdout.
        """
        # Verificar integridade dos arquivos de teste antes do review
        if test_hashes is not None:
            from inner_loop import InnerLoop
            il = InnerLoop(str(self.project_path), verbose=False)
            modified = il.check_test_integrity(test_hashes)
            if modified:
                rel_names = [Path(p).name for p in modified]
                il.revert_test_files(modified)
                return HomologationResult(
                    approved=False,
                    summary="VIOLAÇÃO: arquivos de teste foram modificados pelo Executor.",
                    feedback=(
                        f"O Executor modificou arquivo(s) de teste protegido(s): "
                        f"{', '.join(rel_names)}. Alterações revertidas via git. "
                        f"PROIBIDO modificar test_*.py — implemente apenas o código de produção."
                    ),
                    fix_suggestion=(
                        "Não altere os arquivos test_*.py. "
                        "Implemente apenas o código de produção que faz os testes passarem."
                    ),
                )

        prompt = self._build_review_prompt(task, context, attempt)
        self._vlog("→", prompt)

        try:
            result = subprocess.run(
                [
                    "nice", "-n", "15",  # menor prioridade — evita saturar CPUs junto com o processo principal
                    self.claude_bin,
                    "--print",      # modo não-interativo
                    "--output-format", "json",
                ],
                input=prompt,   # stdin evita limite ARG_MAX com prompts que incluem conteúdo de arquivos
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=180,  # 3 min max para review
            )

            if result.returncode != 0:
                return HomologationResult(
                    error=f"Claude Code saiu com código {result.returncode}: "
                          f"{result.stderr[:500]}",
                    error_kind="infra",
                )

            if not result.stdout.strip():
                # stdout vazio com returncode 0 — stderr pode ter info
                stderr_hint = result.stderr[:200] if result.stderr else "sem stderr"
                return HomologationResult(
                    error=f"Claude Code retornou stdout vazio (stderr: {stderr_hint})",
                    error_kind="infra",
                )

            self._vlog("←", result.stdout[:800])
            return self._parse_response(result.stdout)

        except subprocess.TimeoutExpired:
            return HomologationResult(
                error="Claude Code excedeu o timeout de 180s no review",
                error_kind="infra",
            )
        except FileNotFoundError:
            return HomologationResult(
                error=(
                    f"Binário do Claude Code não encontrado: '{self.claude_bin}' "
                    f"— verifique SQUIRE_CLAUDE_BIN"
                ),
                error_kind="config",
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

        viking_section = ""
        try:
            viking_ctx = _viking.load_viking_context(self.project_path)
            if viking_ctx.strip():
                viking_section = f"\n\n## Restrições de domínio (Padrão Viking)\n{viking_ctx}"
        except Exception:
            pass

        viking_checklist = (
            "5. O código respeita as restrições de domínio do Padrão Viking (se definidas acima)?"
            if viking_section else ""
        )

        return f"""Você está fazendo homologação de código como um tech lead.

## Contexto
Task: {task.title}
Descrição: {task.description}
Tentativa de homologação: {attempt} de {task.max_homologation_attempts}
Testes: {context.tests_passing} passando, {context.tests_failing} falhando
{files_section}
{previous_section}{viking_section}

## O que avaliar
1. O código resolve o que a task pede? (verifique se os arquivos EXIGIDOS pela descrição foram criados)
2. Há edge cases não cobertos pelos testes?
3. O código é legível e segue boas práticas?
4. Tem problemas de segurança ou performance óbvios?
{viking_checklist}

## Formato de resposta (JSON estrito)
Responda APENAS com JSON válido, sem markdown:
{{
  "approved": true/false,
  "summary": "Resumo em até 3 linhas curtas do veredicto e razão principal",
  "feedback": "Explicação detalhada da decisão",
  "fix_suggestion": "Se rejeitado: passos concretos e específicos para o agente local corrigir na próxima tentativa (ex: 'Adicionar empty state em CommitLog.tsx quando commits=[]. Usar router.refresh() no lugar de window.location.reload()'). Se aprovado: deixar vazio.",
  "suggestions": ["melhoria opcional 1", "melhoria opcional 2"]
}}"""

    # Limites de segurança para evitar prompts gigantes (node_modules, dist, etc.)
    _MAX_FILES_FOR_REVIEW = 20
    _MAX_REVIEW_CONTENT_BYTES = 80_000  # ~80 KB de conteúdo de código

    def _read_files_for_review(self, files_touched: list[str]) -> str:
        """Lê o conteúdo dos arquivos modificados para incluir no prompt."""
        if not files_touched:
            # Fallback 1: detectar mudanças via git (staged + working-tree + untracked)
            files_touched = self._git_fallback_files()
        if not files_touched:
            # Fallback 2: arquivos de código mais recentes do repo (últimos 5 por mtime)
            files_touched = self._recent_code_files()
        if not files_touched:
            return "\n\nNenhum arquivo foi modificado/criado nesta tentativa."

        # Limitar número de arquivos para não inflar o prompt
        if len(files_touched) > self._MAX_FILES_FOR_REVIEW:
            files_touched = files_touched[:self._MAX_FILES_FOR_REVIEW]

        parts = ["\n\nArquivos modificados/detectados no repositório:"]
        total_bytes = 0
        for rel_path in files_touched:
            if total_bytes >= self._MAX_REVIEW_CONTENT_BYTES:
                parts.append(f"\n(conteúdo truncado — limite de {self._MAX_REVIEW_CONTENT_BYTES // 1000}KB atingido)")
                break
            full_path = self.project_path / rel_path
            try:
                lines = full_path.read_text(encoding="utf-8").splitlines()
                content = "\n".join(lines[:200])
                if len(lines) > 200:
                    content += f"\n... (truncado — {len(lines)} linhas no total)"
                entry = f"\n### {rel_path}\n```\n{content}\n```"
                total_bytes += len(entry.encode("utf-8"))
                parts.append(entry)
            except Exception as e:
                parts.append(f"\n### {rel_path}\n(erro ao ler: {e})")

        return "\n".join(parts)

    def _git_fallback_files(self) -> list[str]:
        """Detecta arquivos modificados via git quando files_touched não foi populado.

        Filtra para arquivos de código/config — exclui node_modules, dist etc.
        """
        import subprocess
        from backends import _is_source_file
        try:
            files: list[str] = []
            for cmd in (
                ["git", "diff", "--name-only", "HEAD"],
                ["git", "diff", "--name-only", "--cached", "HEAD"],
                ["git", "ls-files", "--others", "--exclude-standard"],
            ):
                p = subprocess.run(cmd, cwd=str(self.project_path),
                                   capture_output=True, text=True, timeout=10)
                files.extend(f.strip() for f in p.stdout.splitlines() if f.strip())
            return [f for f in dict.fromkeys(files) if _is_source_file(f)]
        except Exception:
            return []

    def _recent_code_files(self, max_files: int = 5) -> list[str]:
        """Retorna os arquivos de código mais recentes do repo (por mtime)."""
        extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}
        try:
            candidates = [
                p for p in self.project_path.rglob("*")
                if p.is_file() and p.suffix in extensions
                and ".git" not in p.parts
                and "node_modules" not in p.parts
            ]
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return [str(p.relative_to(self.project_path)) for p in candidates[:max_files]]
        except Exception:
            return []

    def _parse_response(self, stdout: str) -> HomologationResult:
        """Parseia a resposta do Claude Code."""
        usage: Optional[TokenUsage] = None
        try:
            # Claude Code com --output-format json retorna estruturado
            data = json.loads(stdout)

            # Extrai custo + tokens do envelope ANTES de descer no conteúdo —
            # mesmo se o parsing do review interno falhar, queremos contabilizar
            # o custo da chamada que foi efetivamente feita.
            usage = _extract_usage_from_claude_json(data)

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
                try:
                    review = json.loads(clean)
                except json.JSONDecodeError:
                    # Claude às vezes envolve o JSON em prosa ("Aqui está a
                    # análise: {...}") — extrai o primeiro objeto JSON válido
                    # em vez de queimar a rodada com Parse error.
                    review = _extract_json_object(clean)
                    if review is None:
                        raise
            elif isinstance(content, dict):
                review = content
            else:
                return HomologationResult(
                    error=f"Unexpected response format: {type(content)}",
                    error_kind="infra",
                    usage=usage,
                )

            return HomologationResult(
                approved=review.get("approved", False),
                summary=review.get("summary", ""),
                feedback=review.get("feedback", ""),
                fix_suggestion=review.get("fix_suggestion", ""),
                suggestions=review.get("suggestions", []),
                usage=usage,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # Se não conseguiu parsear, trata como rejeição
            # com o texto bruto como feedback. Ainda assim retorna o usage
            # se já foi extraído (a chamada custou mesmo sem output válido).
            return HomologationResult(
                approved=False,
                feedback=f"Não foi possível parsear a resposta: {stdout[:500]}",
                error=f"Parse error: {e}",
                error_kind="infra",
                usage=usage,
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
        verbose: bool = True,
    ):
        self.project_path = Path(project_path)
        self.claude_bin = claude_bin
        self.verbose = verbose

    def _vlog(self, arrow: str, text: str, max_lines: int = 3) -> None:
        if not self.verbose:
            return
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        lines = [l for l in text.splitlines() if l.strip()][:max_lines]
        for i, line in enumerate(lines):
            prefix = f"┊{arrow}" if i == 0 else "┊ "
            print(f"[{ts}]   {prefix} {line[:120]}")

    def implement_directly(
        self,
        task: Task,
        context: LLMContextSummary,
        rejection_context: str = "",
    ) -> tuple[list[str], Optional[TokenUsage]]:
        """
        Modo de emergência: quando o LLM local não consegue resolver após N rodadas,
        pede ao Claude Code para implementar diretamente.

        Retorna (arquivos_escritos, usage). Se falhar, retorna ([], None).
        """
        from backends import parse_and_apply_files

        rejection_section = (
            f"\n\nHistórico de rejeições:\n{rejection_context}"
            if rejection_context else ""
        )

        prompt = f"""O LLM local falhou em implementar esta task após múltiplas rodadas.
Você precisa implementar diretamente.

Task: {task.title}
Descrição: {task.description}
Projeto em: {self.project_path}
Arquivos já existentes: {', '.join(context.files_touched) or 'nenhum'}
Testes passando: {context.tests_passing}, falhando: {context.tests_failing}
Último erro: {context.last_error or 'N/A'}
{rejection_section}

Implemente a task completa. Retorne os arquivos no formato:
```filepath:caminho/relativo/arquivo.ts
// conteúdo completo do arquivo
```

Cada arquivo deve ser completo e funcional. Não use TODOs nem esqueletos.
MESMO que a correção seja pequena (uma linha, um campo), retorne o arquivo
INTEIRO modificado nesse formato — respostas em prosa ou diff são descartadas."""

        self._vlog("→", prompt)
        try:
            result = subprocess.run(
                [self.claude_bin, "--print", "--output-format", "json"],
                input=prompt,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=config.IMPLEMENT_TIMEOUT_SECONDS,
            )
            if result.returncode != 0 or not result.stdout.strip():
                print(
                    f"⚠ implement_directly: claude saiu com código "
                    f"{result.returncode} (stderr: {result.stderr[:200] or 'vazio'})"
                )
                return [], None
            self._vlog("←", result.stdout)
            text, usage = _unwrap_claude_json(result.stdout)
            files = parse_and_apply_files(text, self.project_path)
            if not files:
                preview = (text or "")[:300].replace("\n", " ")
                print(f"⚠ implement_directly: resposta sem blocos filepath — início: {preview!r}")
            return files, usage
        except subprocess.TimeoutExpired:
            print(
                f"⚠ implement_directly: claude excedeu o timeout de "
                f"{config.IMPLEMENT_TIMEOUT_SECONDS}s (SQUIRE_IMPLEMENT_TIMEOUT)"
            )
            return [], None
        except FileNotFoundError:
            print(
                f"⚠ implement_directly: binário '{self.claude_bin}' não "
                f"encontrado no PATH — verifique SQUIRE_CLAUDE_BIN/PATH"
            )
            return [], None

    def unblock(
        self,
        task: Task,
        context: LLMContextSummary,
    ) -> tuple[str, Optional[TokenUsage]]:
        """
        Pede ao Claude Code para analisar o erro e sugerir um caminho.
        Retorna (instruções, usage) — instruções vão de volta ao LLM local
        como extra_instructions.
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

        self._vlog("→", prompt)
        try:
            result = subprocess.run(
                [self.claude_bin, "--print", "--output-format", "json"],
                input=prompt,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                self._vlog("←", result.stdout)
                text, usage = _unwrap_claude_json(result.stdout)
                return text.strip(), usage
            return "", None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "", None


def _unwrap_claude_json(stdout: str) -> tuple[str, Optional[TokenUsage]]:
    """Extrai (texto, usage) de stdout JSON do Claude Code.

    Quando o stdout não é JSON válido (ex: Claude rodando sem --output-format json),
    retorna (stdout, None) para preservar compatibilidade com callers antigos.
    """
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return stdout, None
    text = data.get("result") or data.get("content") or ""
    if not isinstance(text, str):
        text = stdout
    return text, _extract_usage_from_claude_json(data)
