#!/usr/bin/env python3
"""
Orquestrador principal.

Ciclo de vida:
1. Lê checkpoint (ou cria novo a partir do tasks.json)
2. Adquire session lock
3. Para cada task pendente:
   a. Inner loop: LLM local implementa + testa
   b. Homologação: Claude Code valida
   c. Checkpoint persistido a cada transição
4. Ao final, libera lock e atualiza stats

Uso:
    python squire.py <project-id>                    # execução normal
    python squire.py <project-id> --resume            # retoma de crash
    python squire.py <project-id> --dry-run           # mostra o que faria
    python squire.py rm <project-id>                  # remove projeto (com confirmação)
"""

from __future__ import annotations

import argparse
import random
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import accounting
import checkpoint as ckpt
import config
import gitops
from inner_loop import InnerLoop
from homologator import Homologator, HomologationResult, TechnicalEscalation
from rate_limiter import RateLimiter
from models import (
    Actor,
    AlertSeverity,
    Checkpoint,
    CommitLog,
    CommitSummary,
    CursorStep,
    Cursor,
    EventType,
    HistoryEvent,
    ProjectStatus,
    TaskStatus,
    TestAuthor,
    TokenUsage,
)


def log(msg: str, level: str = "info") -> None:
    """Log simples com timestamp."""
    ts = datetime.now().astimezone().strftime("%H:%M:%S")
    prefix = {"info": "→", "ok": "✓", "warn": "⚠", "error": "✗"}
    print(f"[{ts}] {prefix.get(level, '→')} {msg}")


class Squire:
    """Loop principal do squire."""

    def __init__(self, project_id: str, dry_run: bool = False, verbose: bool = True):
        self.project_id = project_id
        self.dry_run = dry_run
        self.verbose = verbose
        self.session_id = f"sess-{datetime.now(timezone.utc):%Y%m%d-%H%M}-{uuid.uuid4().hex[:6]}"

        # Carregar estado
        self.project = ckpt.load_project(project_id)
        if not self.project:
            log(f"Projeto '{project_id}' não encontrado.", "error")
            sys.exit(1)

        self.task_list = ckpt.load_tasks(project_id)
        self.cp = ckpt.load_checkpoint(project_id) or Checkpoint(
            session_id=self.session_id,
        )

        # Componentes
        backend_name = self.project.coding_backend or config.CODING_BACKEND
        self.inner_loop = InnerLoop(self.project.repo_path, backend=backend_name, verbose=verbose)
        self.homologator = Homologator(self.project.repo_path, verbose=verbose)
        self.escalation = TechnicalEscalation(self.project.repo_path, verbose=verbose)
        self.rate_limiter = RateLimiter(self.cp.rate_limit)

        # Stats
        self.stats = ckpt.load_stats()
        # Contadores desta sessão apenas (não persistidos no global-stats)
        self.session_local_calls: int = 0
        self.session_cc_calls: int = 0
        self.session_cost_usd: float = 0.0

        # Heartbeat thread
        self._heartbeat_stop = threading.Event()

    # ── Cost accounting helpers ────────────────────────────────────

    def _account_call(self, usage: TokenUsage | None, task=None, cc_call: bool = True) -> float:
        """
        Contabiliza tokens/custo de uma chamada que já aconteceu.

        Delega para accounting.record_usage (compartilhado com `squire fix`)
        e acumula o custo da sessão. Retorna o custo registrado para uso em
        logs e para passar a `rate_limiter.record_call(cost_usd=…)` no caller.
        """
        cost = accounting.record_usage(self.stats, usage, task=task, cc_call=cc_call)
        self.session_cost_usd += cost
        return cost

    def _review_with_infra_retry(self, task, test_hashes):
        """
        Chama o review do homologador com um retry gratuito para falhas de
        infra (parse error, timeout, stdout vazio) — a rodada de homologação
        não é consumida pelo retry, só pelo veredito. Cada chamada real é
        contabilizada individualmente (custo + rate limit).
        """
        result = None
        for attempt in range(2):
            result = self.homologator.review(
                task=task,
                context=self.cp.llm_context,
                attempt=task.homologation_attempt,
                test_hashes=test_hashes,
            )
            cost = self._account_call(result.usage, task=task, cc_call=True)
            self.rate_limiter.record_call(cost_usd=cost)
            self.stats.daily_claude_code_calls += 1
            self.session_cc_calls += 1

            if (
                result.error
                and getattr(result, "error_kind", None) == "infra"
                and attempt == 0
                and self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD)
            ):
                log(f"Falha de infra na homologação ({result.error}) — retry gratuito 1/1", "warn")
                time.sleep(10)
                continue
            return result
        return result

    def _log_verdict(self, task, result, source: str = "session") -> None:
        """Persiste o veredito completo em homologation_log.json.

        Erros de infra não chegam aqui (não são vereditos). O log preserva
        feedback/fix_suggestion na íntegra — o que rejection_summaries trunca.
        """
        from models import HomologationLogEntry
        try:
            ckpt.append_homologation_entry(self.project_id, HomologationLogEntry(
                task_id=task.id,
                attempt=task.homologation_attempt,
                approved=result.approved,
                summary=result.summary or "",
                feedback=result.feedback or "",
                fix_suggestion=result.fix_suggestion or "",
                suggestions=result.suggestions or [],
                source=source,
                cost_usd=result.usage.cost_usd if result.usage else 0.0,
                model=(result.usage.model or None) if result.usage else None,
            ))
        except Exception as e:
            log(f"Falha ao gravar homologation_log: {e}", "warn")

    def _record_completion_stats(self, task) -> None:
        """
        Atualiza contadores diários após uma task concluída, incluindo a
        taxa de aprovação na 1ª homologação. Tasks com skip_homologation
        ficam de fora da taxa (são auto-aprovadas e inflariam o número).
        """
        self.stats.tasks_completed_today += 1
        if task.skip_homologation:
            return
        accounting.record_homologated(
            self.stats, first_try=task.homologation_attempt == 1
        )

    def _task_budget_exceeded(self, task) -> bool:
        """True se o custo acumulado da task ultrapassou seu cap (Task.max_usd ou global)."""
        cap = task.max_usd if task.max_usd and task.max_usd > 0 else config.PER_TASK_USD_CAP
        if cap <= 0:
            return False
        return float(task.cost_usd or 0.0) >= cap

    # ── Heartbeat ──────────────────────────────────────────────────

    def _heartbeat_loop(self):
        """Thread que atualiza o heartbeat periodicamente."""
        while not self._heartbeat_stop.wait(config.HEARTBEAT_INTERVAL_SECONDS):
            ckpt.heartbeat(self.project_id, self.cp)
            ckpt.renew_lock(self.session_id)

    def _start_heartbeat(self):
        t = threading.Thread(target=self._heartbeat_loop, daemon=True)
        t.start()

    def _stop_heartbeat(self):
        self._heartbeat_stop.set()

    # ── Proteção de working tree ───────────────────────────────────

    def _auto_snapshot_commit(self, task_id: str) -> None:
        """
        Protege o working tree antes de cada task fazendo auto-commit de quaisquer
        alterações não commitadas.

        Isso previne que os agentes (opencode, litellm) revertam silenciosamente
        trabalho anterior via `git checkout`. Toda alteração committada é recuperável
        via `git log`.

        Se o repo ainda não tem nenhum commit (HEAD não existe), apenas loga aviso
        e retorna — não é possível commitar sem HEAD.
        """
        repo = self.project.repo_path
        try:
            # Verificar se working tree está sujo (staged ou unstaged)
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo, capture_output=True, text=True, timeout=10,
            )
            if status.returncode != 0:
                log(f"git status falhou em {repo} — pulando snapshot", "warn")
                return
            if not status.stdout.strip():
                return  # working tree limpo, nada a fazer

            n_files = len(status.stdout.strip().splitlines())
            log(f"Working tree sujo ({n_files} arquivo(s)) — criando snapshot antes de {task_id}", "warn")

            # Verificar se o repo tem commits — snapshot só faz sentido com HEAD
            # (sem HEAD, o primeiro commit deve ser da própria task, não do snapshot)
            has_commits = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=repo, capture_output=True, timeout=5,
            ).returncode == 0
            if not has_commits:
                log("Repo sem commits ainda — snapshot adiado (HEAD não existe)", "info")
                return

            msg = f"chore: auto-snapshot before {task_id}"
            outcome = gitops.commit_all(repo, msg)
            if outcome == "committed":
                log(f"Snapshot commitado: {msg}", "ok")
            elif outcome.startswith("failed"):
                log(f"Falha ao commitar snapshot: {outcome[8:][:100]}", "warn")
        except Exception as e:
            log(f"Erro ao criar snapshot: {e}", "warn")

    def _commit_task_completion(self, task) -> None:
        """
        Commita todas as alterações da task após aprovação na homologação.

        Garante que o trabalho aprovado está no git antes que o próximo agente
        comece a trabalhar — impedindo que um `git checkout` do próximo ciclo
        reverta o código recém-aprovado.
        """
        msg = f"feat: [{task.id}] {task.title[:60]}"
        outcome = gitops.commit_all(self.project.repo_path, msg)
        if outcome == "committed":
            log(f"Task commitada: {msg}", "ok")
            self._refresh_commits_json()
        elif outcome == "nothing":
            log("Nada para commitar (working tree já limpo)", "info")
        else:
            log(f"Falha ao commitar task: {outcome[8:][:100]}", "warn")

    def _refresh_commits_json(self, limit: int = 100) -> None:
        """
        Recompila projects/<id>/commits.json a partir do git log do repo.

        O dashboard lê este arquivo em vez de fazer git log no container —
        evita shell-exec em runtime, ignora repos sem .git e mantém
        diff_summary acessível para a UI.

        Sempre escreve o arquivo, mesmo em falha: o dashboard depende disso
        para diferenciar "projeto recém-criado, sem commits" de "arquivo
        sumiu". Em falha, `CommitLog.error` carrega o motivo.
        """
        repo = self.project.repo_path
        commits: list[CommitSummary] = []
        error: Optional[str] = None
        try:
            fmt = "%H%x1f%s%x1f%aI%x1f"
            log_out = subprocess.run(
                ["git", "log", f"-n{limit}", f"--format={fmt}", "--name-only"],
                cwd=repo, capture_output=True, text=True, timeout=10,
            )
            if log_out.returncode != 0:
                stderr = log_out.stderr.strip()[:200] or f"exit {log_out.returncode}"
                error = f"git log falhou: {stderr}"
            else:
                for block in log_out.stdout.split("\n\n"):
                    block = block.strip()
                    if not block:
                        continue
                    header, _, files_block = block.partition("\n")
                    parts = header.split("\x1f")
                    if len(parts) < 3:
                        continue
                    sha, message, ts = parts[0], parts[1], parts[2]
                    files = [ln for ln in files_block.split("\n") if ln.strip()]
                    try:
                        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        when = datetime.now(timezone.utc)
                    commits.append(CommitSummary(
                        sha=sha,
                        message=message,
                        timestamp=when,
                        diff_summary=f"{len(files)} arquivo(s) alterado(s)",
                        files_changed=files,
                    ))
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            log(f"Falha ao gerar commits.json: {e}", "warn")

        ckpt.save_commits(self.project.id, CommitLog(commits=commits, error=error))

    # ── Buscar próxima task ────────────────────────────────────────

    def _find_current_task(self):
        """Encontra a task apontada pelo cursor, ou a próxima pendente."""
        cursor_id = self.cp.cursor.current_task_id

        # Se o cursor aponta pra uma task, usar ela
        if cursor_id:
            for task in self.task_list.tasks:
                if task.id == cursor_id and task.status not in (
                    TaskStatus.completed, TaskStatus.blocked
                ):
                    return task

        # Senão, pegar a primeira pendente ou em andamento
        for task in self.task_list.tasks:
            if task.status in (TaskStatus.pending, TaskStatus.implementing):
                return task

        return None

    # ── Persistir estado ───────────────────────────────────────────

    def _save_state(self):
        """Persiste todo o estado — chamado nos pontos de checkpoint."""
        self.cp.rate_limit = self.rate_limiter.state
        ckpt.save_checkpoint(self.project_id, self.cp)
        ckpt.save_tasks(self.project_id, self.task_list)
        ckpt.save_project(self.project_id, self.project)
        ckpt.save_stats(self.stats)

    def _record_event(self, event_type: EventType, task_id: str = None,
                      attempt: int = None, summary: str = "",
                      actor: Actor = Actor.squire):
        ckpt.append_event(self.project_id, HistoryEvent(
            type=event_type,
            task_id=task_id,
            attempt=attempt,
            summary=summary,
            actor=actor,
        ))

    # ── Detecção de loop e sem progresso ───────────────────────────

    def _is_looping(self, task) -> bool:
        """
        Detecta se o LLM está preso no mesmo padrão de erro há N rejeições consecutivas.

        Compara as últimas LOOP_DETECT_THRESHOLD summaries de rejeição:
        se 4+ palavras significativas aparecem em todas elas, é um loop.
        """
        threshold = config.LOOP_DETECT_THRESHOLD
        if len(task.rejection_summaries) < threshold:
            return False

        stopwords = {
            "o", "a", "e", "de", "da", "do", "que", "em", "um", "uma", "para",
            "com", "não", "se", "por", "mas", "ou", "na", "no", "as", "os",
            "é", "foi", "ser", "está", "tem", "há", "este", "esta", "isso",
        }
        last_n = task.rejection_summaries[-threshold:]
        word_sets = [
            set(s.lower().split()) - stopwords
            for s in last_n
        ]
        if not word_sets:
            return False
        common = word_sets[0].copy()
        for ws in word_sets[1:]:
            common &= ws
        # 4+ palavras significativas em comum indica loop
        return len(common) >= 4

    def _force_escalation(self, task, context_feedback: str) -> str:
        """
        Força escalação técnica imediata ao Claude Code.
        Usado quando loop detectado ou sem progresso por N ciclos.
        Retorna as instruções para o próximo inner loop.
        """
        if not self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD):
            log("Rate limit ou budget ativo — não é possível escalar agora", "warn")
            return context_feedback

        log("Loop detectado — escalação forçada ao Claude Code", "warn")
        extra, usage = self.escalation.unblock(task, self.cp.llm_context)
        cost = self._account_call(usage, task=task, cc_call=True)
        self.rate_limiter.record_call(cost_usd=cost)
        self.stats.daily_claude_code_calls += 1
        self.session_cc_calls += 1
        task.claude_code_assisted = True
        if extra:
            log(f"Instruções de desbloqueio recebidas do Claude Code (${cost:.3f})", "ok")
        return extra or context_feedback

    # ── Fase RED (TDD) ─────────────────────────────────────────────

    def _run_red_phase(self, task) -> None:
        """
        Fase RED: escreve testes falhos uma única vez antes da implementação.

        Para test_author=claude: Claude Code escreve os testes.
        Para test_author=local: LLM local escreve os testes.
        Não conta como tentativa de implementação.
        """
        log(f"Fase RED — escrevendo testes: [{task.id}] {task.title}")
        self.cp.cursor.step = CursorStep.red_phase
        self._save_state()

        if self.dry_run:
            log("[dry-run] Simulando fase RED", "warn")
            return

        red_prompt = (
            f"## Fase RED — Escreva APENAS os testes (não implemente ainda)\n\n"
            f"Task: {task.title}\n"
            f"Descrição: {task.description}\n"
            f"Projeto em: {self.inner_loop.project_path}\n\n"
            f"Escreva os testes que definem o comportamento esperado. "
            f"Os testes DEVEM FALHAR agora pois o código de produção ainda não existe. "
            f"Crie apenas arquivos de teste (test_*.py ou *.test.ts/tsx). "
            f"NÃO implemente nenhuma função, classe ou módulo de produção."
        )

        if task.test_author == TestAuthor.claude:
            if not self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD):
                log("Rate limit ou budget ativo — fase RED (Claude) adiada", "warn")
                return
            try:
                result = subprocess.run(
                    [self.homologator.claude_bin, "--print", "--output-format", "json"],
                    input=red_prompt,
                    cwd=str(self.inner_loop.project_path),
                    capture_output=True, text=True, timeout=180,
                )
                from homologator import _unwrap_claude_json
                text, usage = _unwrap_claude_json(result.stdout)
                cost = self._account_call(usage, task=task, cc_call=True)
                self.rate_limiter.record_call(cost_usd=cost)
                self.stats.daily_claude_code_calls += 1
                self.session_cc_calls += 1
                if result.returncode == 0 and text.strip():
                    from backends import parse_and_apply_files
                    files = parse_and_apply_files(text, self.inner_loop.project_path)
                    log(f"Fase RED (Claude): {len(files)} arquivo(s) criado(s) (${cost:.3f})", "ok")
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                log(f"Fase RED (Claude) falhou: {e}", "warn")
        else:
            # LLM local escreve os testes
            red_task = task.model_copy(update={"description": red_prompt, "attempts": 0})
            result = self.inner_loop.execute(
                task=red_task,
                previous_context=None,
                extra_instructions="",
                test_hashes=None,  # sem proteção — é a fase RED que cria os testes
            )
            self.stats.daily_local_llm_calls += 1
            self.session_local_calls += 1
            self._account_call(result.usage, task=task, cc_call=False)
            if result.files_touched:
                log(f"Fase RED (local): {len(result.files_touched)} arquivo(s) criado(s)", "ok")
            elif result.error:
                log(f"Fase RED (local) erro: {result.error}", "warn")

    # ── Inner Loop (uma task) ──────────────────────────────────────

    def _run_inner_loop(
        self,
        task,
        homologation_feedback: str = "",
        test_hashes: dict[str, str] | None = None,
    ) -> bool:
        """
        Executa o inner loop até os testes passarem ou esgotar tentativas.
        Retorna True se os testes passaram.
        """
        extra_instructions = homologation_feedback

        while task.attempts < task.max_attempts:
            task.attempts += 1
            task.status = TaskStatus.implementing
            self.cp.cursor.step = CursorStep.llm_execution
            self.cp.cursor.attempt = task.attempts

            log(f"Inner loop: {task.title} (tentativa {task.attempts}/{task.max_attempts})")

            if self.dry_run:
                log("[dry-run] Simulando execução do LLM local", "warn")
                return True

            result = self.inner_loop.execute(
                task=task,
                previous_context=self.cp.llm_context,
                extra_instructions=extra_instructions,
                test_hashes=test_hashes,
            )

            # Atualizar contexto no checkpoint
            if result.context_summary:
                self.cp.llm_context = result.context_summary

            # Atualizar stats (inclui custo do backend local, geralmente 0)
            self.stats.daily_local_llm_calls += 1
            self.session_local_calls += 1
            self._account_call(result.usage, task=task, cc_call=False)
            if self.project_id not in self.stats.projects_touched_today:
                self.stats.projects_touched_today.append(self.project_id)

            # Per-task budget cap (Task.max_usd ou config.PER_TASK_USD_CAP)
            if self._task_budget_exceeded(task):
                cap = task.max_usd or config.PER_TASK_USD_CAP
                log(
                    f"Task budget esgotado (${task.cost_usd:.2f} >= ${cap:.2f}) — pausando task",
                    "warn",
                )
                ckpt.add_alert(
                    self.project_id, "task_budget_exceeded",
                    f"Task '{task.title}' atingiu cap de ${cap:.2f}",
                    task_id=task.id, severity=AlertSeverity.warning,
                )
                self._save_state()
                return False

            # Checkpoint após cada iteração
            self._save_state()

            if result.error:
                log(f"Erro fatal no inner loop: {result.error}", "error")
                self._record_event(
                    EventType.tests_failed, task.id, task.attempts,
                    f"Erro fatal: {result.error}", Actor.local_llm,
                )
                continue

            # Detectar ciclos sem progresso (nenhum arquivo modificado)
            if not result.files_touched:
                task.no_progress_streak += 1
                log(
                    f"[WARN] Backend não modificou nenhum arquivo "
                    f"({task.no_progress_streak}/{config.NO_PROGRESS_THRESHOLD} consecutivos)",
                    "warn",
                )
                if task.no_progress_streak >= config.NO_PROGRESS_THRESHOLD:
                    log("Sem progresso por N ciclos — forçando escalação", "warn")
                    extra_instructions = self._force_escalation(task, extra_instructions)
                    task.no_progress_streak = 0
            else:
                task.no_progress_streak = 0

            if result.success:
                if result.tests_skipped:
                    log("Sem testes configurados — avançando para homologação", "ok")
                else:
                    log(f"Testes passando ({result.tests_passing} ok)", "ok")
                self._record_event(
                    EventType.tests_passed, task.id, task.attempts,
                    "sem testes configurados" if result.tests_skipped
                    else f"{result.tests_passing} testes passando",
                    Actor.local_llm,
                )
                return True

            log(
                f"Testes falhando: {result.tests_failing} "
                f"({result.test_output[:100]}...)",
                "warn",
            )
            self._record_event(
                EventType.tests_failed, task.id, task.attempts,
                f"{result.tests_failing} testes falhando: "
                f"{result.test_output[:200]}",
                Actor.local_llm,
            )

            # A cada 5 tentativas falhas, pedir ajuda técnica ao Claude Code
            if task.attempts % 5 == 0 and task.attempts < task.max_attempts:
                log("Pedindo ajuda técnica ao Claude Code...", "warn")
                self.rate_limiter.wait_if_needed()

                if self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD):
                    extra_instructions, usage = self.escalation.unblock(
                        task, self.cp.llm_context,
                    )
                    cost = self._account_call(usage, task=task, cc_call=True)
                    self.rate_limiter.record_call(cost_usd=cost)
                    self.stats.daily_claude_code_calls += 1
                    self.session_cc_calls += 1
                    task.claude_code_assisted = True
                    if extra_instructions:
                        log(f"Recebeu orientação do Claude Code (${cost:.3f})", "ok")

        # Esgotou tentativas
        log(f"Inner loop esgotou {task.max_attempts} tentativas", "error")
        return False

    # ── Espera produtiva ───────────────────────────────────────────

    def _wait_productively(
        self,
        task,
        last_feedback: str,
        test_hashes: dict[str, str] | None = None,
    ) -> None:
        """
        Enquanto o rate limit estiver ativo, continua refinando o código
        com o feedback da última homologação, em vez de dormir.
        Quando a janela resetar, retorna e permite nova tentativa de homologação.
        """
        while not self.rate_limiter.can_call():
            wait = self.rate_limiter.wait_seconds()
            log(
                f"Rate limit: {wait // 60:.0f}min restantes — "
                "continuando inner loop enquanto aguarda...", "warn"
            )
            task.attempts = 0
            self._run_inner_loop(task, homologation_feedback=last_feedback, test_hashes=test_hashes)

    # ── Gate mecânico pré-homologação ─────────────────────────────

    def _pre_homologation_checks(self, task) -> list[str]:
        """
        Verificações mecânicas multi-linguagem executadas antes de cada chamada ao Claude Code.

        Se retornar uma lista não-vazia, o ciclo volta ao inner loop com as violations
        como feedback — sem gastar uma chamada de rate limit.

        Linguagens suportadas (auto-detectadas pelo arquivo de projeto):
        - TypeScript  (tsconfig.json)
        - Python      (pyproject.toml ou *.py na raiz)
        - Go          (go.mod)
        - Rust        (Cargo.toml)
        - Zig         (build.zig)
        - Java/Kotlin (build.gradle / build.gradle.kts / pom.xml)
        - Ruby        (Gemfile)

        Checks universais (todas as linguagens):
        - Arquivo de teste: se task.tdd=True, deve existir pelo menos um test file
        """
        violations: list[str] = []
        repo = Path(self.project.repo_path)

        # ── Utilitário: diff das linhas adicionadas desde HEAD ──────
        def _added_lines() -> list[str]:
            try:
                proc = subprocess.run(
                    ["git", "diff", "HEAD", "--unified=0"],
                    cwd=str(repo), capture_output=True, text=True, timeout=10,
                )
                return [
                    l[1:]  # remove o '+' inicial
                    for l in proc.stdout.splitlines()
                    if l.startswith("+") and not l.startswith("+++")
                ]
            except Exception:
                return []

        # ── Utilitário: rodar comando e capturar falha ───────────────
        def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
            try:
                proc = subprocess.run(
                    cmd, cwd=str(repo),
                    capture_output=True, text=True, timeout=timeout,
                )
                return proc.returncode, (proc.stdout + proc.stderr)
            except FileNotFoundError:
                return -1, ""  # ferramenta não instalada — não penalizar
            except subprocess.TimeoutExpired:
                return -1, ""  # timeout — não penalizar

        # ── Universal: arquivos de teste (task.tdd=True) ────────────
        if task.tdd:
            _IGNORE = {".venv", "venv", "__pycache__", "node_modules", "dist",
                       ".next", "target", "zig-out", "zig-cache"}
            _TEST_PATTERNS = [
                "test_*.py", "*_test.py",           # Python
                "*.test.ts", "*.test.tsx",           # TypeScript/React
                "*.spec.ts", "*.spec.tsx",           # TypeScript/React
                "*.test.js", "*.spec.js",            # JavaScript
                "*_test.go",                         # Go
                "*_test.rs",                         # Rust (src/)
                "*_test.zig", "*_test.zig",          # Zig
                "*Test.java", "*Tests.java",         # Java
                "*_spec.rb",                         # Ruby
            ]
            def _has_tests() -> bool:
                for pat in _TEST_PATTERNS:
                    for p in repo.rglob(pat):
                        if not any(part in _IGNORE for part in p.parts):
                            return True
                return False
            if not _has_tests():
                violations.append(
                    "Nenhum arquivo de teste encontrado (task.tdd=True). "
                    "Crie testes antes de avançar para homologação."
                )

        # ── TypeScript ───────────────────────────────────────────────
        if (repo / "tsconfig.json").exists():
            tsc_bin = repo / "node_modules" / ".bin" / "tsc"
            if tsc_bin.exists():
                code, out = _run([str(tsc_bin), "--noEmit"])
                if code not in (0, -1):
                    violations.append(f"TypeScript errors (tsc --noEmit):\n{out[:500]}")

            # Tipo 'any' introduzido — LLMs adicionam para silenciar erros de tipo
            new_any = [l for l in _added_lines()
                       if ": any" in l or "as any" in l or "<any>" in l]
            if new_any:
                violations.append(
                    f"Tipo 'any' introduzido ({len(new_any)} ocorrência(s)). "
                    f"Exemplo: {new_any[0].strip()[:100]}"
                )

        # ── Python ───────────────────────────────────────────────────
        _PYTHON_IGNORE = {".venv", "venv", "__pycache__", "node_modules"}
        _py_files = [
            p for p in repo.rglob("*.py")
            if not any(part in _PYTHON_IGNORE for part in p.parts)
        ]
        if (repo / "pyproject.toml").exists() or list(repo.glob("*.py")):
            import ast as _ast
            syntax_errors: list[str] = []
            for py_file in _py_files:
                try:
                    _ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
                except SyntaxError as e:
                    rel = str(py_file.relative_to(repo))
                    syntax_errors.append(f"  {rel}:{e.lineno}: {e.msg}")
            if syntax_errors:
                violations.append(
                    "Python syntax errors:\n" + "\n".join(syntax_errors[:5])
                )

            # '# type: ignore' introduzido — equivalente ao ': any' do TS
            new_ignores = [l for l in _added_lines() if "# type: ignore" in l]
            if new_ignores:
                violations.append(
                    f"'# type: ignore' introduzido ({len(new_ignores)} ocorrência(s)). "
                    "Corrija o tipo em vez de silenciar o checker."
                )

        # ── Go ───────────────────────────────────────────────────────
        if (repo / "go.mod").exists():
            code, out = _run(["go", "build", "./..."])
            if code not in (0, -1):
                violations.append(f"Go build error:\n{out[:500]}")
            else:
                code2, out2 = _run(["go", "vet", "./..."], timeout=30)
                if code2 not in (0, -1):
                    violations.append(f"go vet:\n{out2[:300]}")

        # ── Rust ─────────────────────────────────────────────────────
        if (repo / "Cargo.toml").exists():
            # cargo check: mais rápido que build (sem codegen), pega todos os erros de tipo
            code, out = _run(["cargo", "check", "--message-format=short"], timeout=120)
            if code not in (0, -1):
                violations.append(f"Rust cargo check:\n{out[:500]}")
            else:
                # clippy: pega patterns problemáticos que LLMs introduzem
                code2, out2 = _run(
                    ["cargo", "clippy", "--", "-D", "warnings"],
                    timeout=120,
                )
                if code2 not in (0, -1):
                    violations.append(f"Rust clippy warnings (tratados como erros):\n{out2[:400]}")

            # #[allow(warnings)] ou unsafe introduzidos para silenciar clippy
            escape_lines = [
                l for l in _added_lines()
                if "#[allow(" in l or "unsafe {" in l or "unsafe fn " in l
            ]
            if escape_lines:
                violations.append(
                    f"'#[allow(...)]' ou 'unsafe' introduzido ({len(escape_lines)} ocorrência(s)). "
                    f"Exemplo: {escape_lines[0].strip()[:100]}"
                )

        # ── Zig ──────────────────────────────────────────────────────
        if (repo / "build.zig").exists():
            code, out = _run(["zig", "build"], timeout=120)
            if code not in (0, -1):
                violations.append(f"Zig build error:\n{out[:500]}")

            # zig fmt --check: formato canônico — LLMs frequentemente quebram
            code2, out2 = _run(["zig", "fmt", "--check", "."], timeout=30)
            if code2 not in (0, -1):
                violations.append(f"Zig format check (zig fmt --check):\n{out2[:300]}")

            # '_ = expr' para descartar erros — equivalente ao ': any'
            discard_lines = [l for l in _added_lines()
                             if l.strip().startswith("_ =") or "catch unreachable" in l]
            if discard_lines:
                violations.append(
                    f"Erro descartado com '_ =' ou 'catch unreachable' "
                    f"({len(discard_lines)} ocorrência(s)). "
                    "Trate o erro explicitamente."
                )

        # ── Java / Kotlin ────────────────────────────────────────────
        _has_gradle = (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists()
        _has_maven  = (repo / "pom.xml").exists()
        if _has_gradle:
            gradlew = repo / "gradlew"
            cmd = [str(gradlew), "compileJava", "--quiet"] if gradlew.exists() \
                  else ["gradle", "compileJava", "--quiet"]
            code, out = _run(cmd, timeout=120)
            if code not in (0, -1):
                violations.append(f"Gradle compile error:\n{out[:500]}")
        elif _has_maven:
            code, out = _run(["mvn", "compile", "-q"], timeout=120)
            if code not in (0, -1):
                violations.append(f"Maven compile error:\n{out[:500]}")

        # ── Ruby ─────────────────────────────────────────────────────
        if (repo / "Gemfile").exists():
            rb_errors: list[str] = []
            for rb_file in repo.rglob("*.rb"):
                if any(part in {"vendor", "node_modules"} for part in rb_file.parts):
                    continue
                code, out = _run(["ruby", "-c", str(rb_file)], timeout=10)
                if code not in (0, -1) and "Syntax OK" not in out:
                    rel = str(rb_file.relative_to(repo))
                    rb_errors.append(f"  {rel}: {out.strip()[:100]}")
            if rb_errors:
                violations.append("Ruby syntax errors:\n" + "\n".join(rb_errors[:5]))

        return violations

    # ── Ciclo de rodadas (Ralph Loop) ─────────────────────────────

    def _run_homologation(self, task) -> bool:
        """
        Executa o ciclo completo de rodadas para uma task.

        Cada rodada = inner loop (até max_attempts) + homologação pelo Claude Code.
        O inner loop roda sempre, independente de os testes passarem ou não.
        Se aprovado em qualquer rodada → True. Se esgotou max_homologation_attempts → False.
        """
        last_feedback = ""  # feedback acumulado da última rejeição
        gate_failures = 0   # violações mecânicas consecutivas sem CC call

        # ── Fase RED: escrever testes antes da implementação ──
        test_hashes: dict[str, str] | None = None
        if task.tdd:
            existing = self.inner_loop.snapshot_test_hashes()
            # Só rodar RED se não há testes ainda e cursor não está além da fase RED
            already_past_red = (
                self.cp.cursor.current_task_id == task.id
                and self.cp.cursor.step not in (None, CursorStep.red_phase)
            )
            if not existing and not already_past_red:
                self._run_red_phase(task)
            test_hashes = self.inner_loop.snapshot_test_hashes()
            if test_hashes:
                log(f"Snapshot: {len(test_hashes)} arquivo(s) de teste protegido(s)", "ok")

        while task.homologation_attempt < task.max_homologation_attempts:
            # Per-task budget cap — aborta a task antes de gastar mais
            if self._task_budget_exceeded(task):
                cap = task.max_usd or config.PER_TASK_USD_CAP
                log(
                    f"Task budget esgotado (${task.cost_usd:.2f} >= ${cap:.2f}) — abortando rodadas",
                    "warn",
                )
                task.homologation_result = "rejected"
                return False

            rodada = task.homologation_attempt + 1
            total  = task.max_homologation_attempts

            # ── Inner loop desta rodada ──
            log(f"Rodada {rodada}/{total} — inner loop: [{task.id}] {task.title}")
            task.attempts = 0
            self._run_inner_loop(task, homologation_feedback=last_feedback, test_hashes=test_hashes)
            # Resultado dos testes é ignorado: sempre avança para homologação

            # Pausa para garantir que o Qwen terminou antes do claude --print
            time.sleep(5)

            # ── Homologação desta rodada ──
            task.homologation_attempt += 1
            task.status = TaskStatus.homologating
            self.cp.cursor.step = CursorStep.homologation
            self.cp.cursor.homologation_attempt = task.homologation_attempt

            log(f"Rodada {rodada}/{total} — homologação: [{task.id}] {task.title}")

            # Auto-aprovação para tasks marcadas como skip_homologation
            if task.skip_homologation:
                log(f"[AUTO-APPROVED] skip_homologation=True", "ok")
                self._record_event(
                    EventType.homologation_approved, task.id, rodada,
                    "Auto-aprovado: skip_homologation=True", Actor.squire,
                )
                task.homologation_result = "approved"
                self._log_verdict(task, HomologationResult(
                    approved=True, summary="Auto-aprovado: skip_homologation=True",
                ))
                return True

            if self.dry_run:
                log("[dry-run] Simulando homologação", "warn")
                return True

            # Se rate limited, refina com inner loop enquanto aguarda
            self._wait_productively(task, last_feedback, test_hashes=test_hashes)

            # Gate mecânico: verificar violations antes de gastar chamada de Claude Code.
            # Máximo 2 gate-retries consecutivos para evitar loop infinito quando o
            # inner loop não consegue corrigir as violations.
            if not self.dry_run and gate_failures < 2:
                violations = self._pre_homologation_checks(task)
                if violations:
                    gate_failures += 1
                    log(
                        f"Gate pré-homologação: {len(violations)} violation(s) "
                        f"(tentativa {gate_failures}/2) — retornando ao inner loop",
                        "warn",
                    )
                    for v in violations:
                        log(f"  • {v[:120]}", "warn")
                    last_feedback = (
                        "## Violations detectadas pelo gate pré-homologação\n"
                        "Corrija estes problemas antes que o código seja revisado:\n\n"
                        + "\n\n".join(f"- {v}" for v in violations)
                    )
                    task.homologation_attempt -= 1  # desfazer incremento — não gastou CC
                    continue
                else:
                    gate_failures = 0  # reset se passou no gate

            if not self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD):
                log("Budget/rate limit ativo — homologação adiada", "warn")
                self._wait_productively(task, last_feedback, test_hashes=test_hashes)
                continue

            result = self._review_with_infra_retry(task, test_hashes)

            self._save_state()

            if result.error:
                log(f"Erro na homologação: {result.error}", "error")
                self._record_event(
                    EventType.homologation_failed, task.id,
                    task.homologation_attempt,
                    f"Erro: {result.error}", Actor.claude_code,
                )
                if result.error_kind == "config":
                    # Erro de configuração não se resolve repetindo rodadas
                    # (ex: binário ausente) — bloqueia a task imediatamente.
                    log("Erro de configuração — abortando homologações desta task", "error")
                    return False
                continue

            verdict_log = result.summary or result.feedback[:100]

            self._log_verdict(task, result)

            if result.approved:
                log(f"Homologação aprovada! {verdict_log}", "ok")
                self._record_event(
                    EventType.homologation_approved, task.id,
                    task.homologation_attempt,
                    result.feedback[:300], Actor.claude_code,
                )
                task.homologation_result = "approved"
                return True

            log(f"Homologação rejeitada: {verdict_log}", "warn")
            self._record_event(
                EventType.homologation_failed, task.id,
                task.homologation_attempt,
                result.feedback[:300], Actor.claude_code,
            )

            # Registrar summary para detecção de loop
            if result.summary:
                task.rejection_summaries.append(result.summary)
                # Manter apenas as últimas 10 para não inflar o checkpoint
                task.rejection_summaries = task.rejection_summaries[-10:]

            # Monta contexto para a próxima rodada: fix_suggestion primeiro (mais acionável),
            # depois summary e feedback como contexto adicional
            parts = []
            if result.fix_suggestion:
                parts.append(f"## O que corrigir\n{result.fix_suggestion}")
            if result.summary:
                parts.append(f"## Resumo da rejeição\n{result.summary}")
            if result.feedback:
                parts.append(f"## Detalhes\n{result.feedback}")
            last_feedback = "\n\n".join(parts) if parts else result.feedback

            # Detectar loop repetitivo — escalar imediatamente se necessário
            if self._is_looping(task):
                log(
                    f"Loop detectado: mesmo erro em "
                    f"{config.LOOP_DETECT_THRESHOLD} rejeições consecutivas",
                    "error",
                )
                last_feedback = self._force_escalation(task, last_feedback)

            # Escalação antecipada para effort:low: após 2 rejeições + loop, CC implementa direto.
            # Para tasks simples que não estão convergindo, evita ciclos extras desnecessários.
            from models import Effort
            is_early_escalation = (
                task.effort == Effort.low
                and task.homologation_attempt >= 2
                and self._is_looping(task)
                and not self.dry_run
            )
            if is_early_escalation:
                log("effort:low + 2 rejeições + loop → Claude Code implementa diretamente", "warn")
                if self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD):
                    files_written, usage = self.escalation.implement_directly(
                        task, self.cp.llm_context,
                        rejection_context="\n".join(task.rejection_summaries[-3:]),
                    )
                    cost = self._account_call(usage, task=task, cc_call=True)
                    self.rate_limiter.record_call(cost_usd=cost)
                    self.stats.daily_claude_code_calls += 1
                    self.session_cc_calls += 1
                    if files_written:
                        log(f"Claude Code escreveu {len(files_written)} arquivo(s) (${cost:.3f})", "ok")
                        task.claude_code_assisted = True
                        self.cp.llm_context.files_touched = files_written
                        last_feedback = ""

            # Penúltima rodada com loop persistente: Claude Code implementa diretamente
            is_penultimate = task.homologation_attempt >= task.max_homologation_attempts - 1
            if is_penultimate and self._is_looping(task) and not self.dry_run:
                log(
                    "Penúltima rodada + loop persistente → "
                    "Claude Code implementa diretamente", "warn"
                )
                if self.rate_limiter.can_afford(config.ESTIMATED_CALL_COST_USD):
                    files_written, usage = self.escalation.implement_directly(
                        task, self.cp.llm_context,
                        rejection_context="\n".join(task.rejection_summaries[-5:]),
                    )
                    cost = self._account_call(usage, task=task, cc_call=True)
                    self.rate_limiter.record_call(cost_usd=cost)
                    self.stats.daily_claude_code_calls += 1
                    self.session_cc_calls += 1
                    if files_written:
                        log(
                            f"Claude Code escreveu {len(files_written)} arquivo(s) (${cost:.3f}) — "
                            "avançando para última homologação", "ok"
                        )
                        task.claude_code_assisted = True
                        # Atualiza contexto com os arquivos escritos pelo Claude Code
                        self.cp.llm_context.files_touched = files_written
                        last_feedback = ""  # Claude Code já implementou, não precisa de feedback

        # Esgotou todas as rodadas
        task.homologation_result = "rejected"
        return False

    # ── Loop Principal ─────────────────────────────────────────────

    def run(self):
        """Executa o loop principal do orquestrador."""
        config.ensure_dirs()

        # Adquirir lock
        if not ckpt.acquire_lock(self.session_id, self.project_id):
            log("Outra sessão está ativa. Abortando.", "error")
            sys.exit(1)

        log(f"Sessão iniciada: {self.session_id}")
        log(f"Projeto: {self.project.name} ({self.project_id})")
        self._record_event(
            EventType.session_started if not self.cp.cursor.current_task_id
            else EventType.session_resumed,
            summary=f"Session {self.session_id}",
        )

        self._start_heartbeat()
        self.project.status = ProjectStatus.implementing

        # Garante que commits.json exista desde a primeira sessão. Sem isto,
        # projetos recém-criados nunca têm o arquivo até a primeira task
        # concluída, e o dashboard mascara ENOENT como "lista vazia".
        self._refresh_commits_json()

        try:
            while True:
                task = self._find_current_task()
                if not task:
                    log("Todas as tasks concluídas ou bloqueadas!", "ok")
                    break

                # Atualizar cursor
                self.cp.cursor.current_task_id = task.id
                self.project.current_task_id = task.id
                self._save_state()

                log(f"\n{'='*50}")
                log(f"Task [{task.id}]: {task.title}")
                log(f"{'='*50}")

                self._record_event(
                    EventType.task_started, task.id,
                    summary=task.title,
                )

                # Snapshot automático: commita alterações pendentes antes do agente iniciar
                self._auto_snapshot_commit(task.id)

                # ── Ciclo de rodadas: inner loop + homologação ──
                homolog_ok = self._run_homologation(task)

                if homolog_ok:
                    # Commitar alterações aprovadas antes de avançar para a próxima task
                    self._commit_task_completion(task)
                    task.status = TaskStatus.completed
                    task.completed_at = datetime.now(timezone.utc)
                    self._record_completion_stats(task)
                    self._record_event(
                        EventType.task_completed, task.id,
                        summary=f"Aprovada na homologação #{task.homologation_attempt}",
                    )
                    log(f"Task concluída: [{task.id}] {task.title} (${task.cost_usd:.3f})", "ok")
                    # Atualizar memória de longo prazo (padrão Ralph Loop)
                    try:
                        import progress as _progress
                        _progress.generate_progress(self.project_id)
                        log("progress.txt atualizado", "ok")
                    except Exception as _pe:
                        log(f"Falha ao atualizar progress.txt: {_pe}", "warn")
                    self._log_remaining_tasks()
                else:
                    task.status = TaskStatus.blocked
                    ckpt.add_alert(
                        self.project_id,
                        "max_homologations_reached",
                        f"Task '{task.title}' falhou {task.max_homologation_attempts} "
                        f"homologações. Último feedback: "
                        f"{self.cp.llm_context.last_error or 'N/A'}",
                        task_id=task.id,
                        severity=AlertSeverity.critical,
                    )
                    self._record_event(
                        EventType.escalation_created, task.id,
                        summary="Homologação esgotada — intervenção necessária",
                    )
                    log(f"Task bloqueada: {task.title}", "error")

                self._save_state()

            # Verificar se todas completaram
            all_done = all(
                t.status in (TaskStatus.completed, TaskStatus.blocked)
                for t in self.task_list.tasks
            )
            if all_done:
                all_ok = all(
                    t.status == TaskStatus.completed
                    for t in self.task_list.tasks
                )
                self.project.status = (
                    ProjectStatus.completed if all_ok
                    else ProjectStatus.blocked
                )

        except KeyboardInterrupt:
            log("\nInterrompido pelo usuário.", "warn")
            self.cp.recovery.resume_action = "continue"

        except Exception as e:
            log(f"Erro não tratado: {e}", "error")
            self.cp.recovery.can_resume = True
            self.cp.recovery.resume_action = "retry_current_subtask"
            self.cp.recovery.blocked_reason = str(e)
            raise

        finally:
            self._stop_heartbeat()
            self._record_event(EventType.session_ended, summary="Sessão finalizada")
            self._save_state()
            ckpt.release_lock()
            log("Lock liberado. Sessão encerrada.")
            self._print_summary()

    def _log_remaining_tasks(self):
        """Exibe o progresso após cada task concluída (só tasks de nível 1)."""
        icons = {
            TaskStatus.completed:    "✓",
            TaskStatus.blocked:      "✗",
            TaskStatus.implementing: "⟳",
            TaskStatus.homologating: "⌛",
            TaskStatus.pending:      "·",
            TaskStatus.testing:      "⧖",
        }
        total = len(self.task_list.tasks)
        done  = sum(1 for t in self.task_list.tasks if t.status == TaskStatus.completed)
        log(f"Progresso: {done}/{total} tasks")
        for t in self.task_list.tasks:
            icon = icons.get(t.status, "?")
            log(f"  {icon} [{t.id}] {t.title}")

    def _print_summary(self):
        """Imprime resumo da sessão."""
        completed = sum(
            1 for t in self.task_list.tasks
            if t.status == TaskStatus.completed
        )
        blocked = sum(
            1 for t in self.task_list.tasks
            if t.status == TaskStatus.blocked
        )
        total = len(self.task_list.tasks)

        session_ratio = self.session_local_calls / max(1, self.session_cc_calls)
        daily_ratio   = self.stats.daily_local_llm_calls / max(1, self.stats.daily_claude_code_calls)

        log(f"\n{'─'*50}")
        log(f"Resumo: {completed}/{total} tasks concluídas, {blocked} bloqueadas")
        log(f"  Esta sessão  →  LLM local: {self.session_local_calls}  |  Claude Code: {self.session_cc_calls}  |  proporção: {session_ratio:.1f}:1")
        log(f"  Hoje (total) →  LLM local: {self.stats.daily_local_llm_calls}  |  Claude Code: {self.stats.daily_claude_code_calls}  |  proporção: {daily_ratio:.1f}:1")
        log(f"  Meta: 30:1")
        # Cost summary — só interessa se algo foi gasto
        if self.session_cost_usd > 0 or self.stats.cost_estimate_usd > 0:
            cap = self.rate_limiter.state.max_daily_usd
            cap_str = f" / ${cap:.2f}" if cap > 0 else ""
            log(f"  Custo sessão →  ${self.session_cost_usd:.3f}  |  Hoje →  ${self.stats.cost_estimate_usd:.3f}{cap_str}  |  tokens: {self.stats.daily_tokens:,}")
            if self.stats.cost_by_model:
                breakdown = "  ".join(
                    f"{m}: ${c:.3f}" for m, c in sorted(self.stats.cost_by_model.items())
                )
                log(f"               por modelo → {breakdown}")
            if self.stats.daily_calls_unknown_cost:
                log(f"               ⚠ {self.stats.daily_calls_unknown_cost} chamada(s) sem usage reportado — custo real pode ser maior")
        log(f"{'─'*50}")


# ── Entrypoint ─────────────────────────────────────────────────────

# Palavras do alfabeto NATO — fáceis de soletrar e difíceis de confirmar por acidente.
_CONFIRM_WORDS = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
    "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
    "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform",
    "victor", "whiskey", "xray", "yankee", "zulu",
]


def cmd_remove(project_id: str) -> None:
    """
    Remove um projeto do estado do squire após confirmação dupla.

    O que é removido: apenas o diretório de estado em STATE_ROOT/projects/<project_id>.
    O repositório de código (repo_path) NÃO é tocado.
    """
    state_dir = config.project_dir(project_id)

    if not state_dir.exists():
        print(f"Projeto '{project_id}' não encontrado em {config.PROJECTS_DIR}.")
        sys.exit(1)

    # Mostrar o que será deletado
    files = list(state_dir.iterdir())
    print(f"\n\033[1;33m⚠  Remoção de projeto: {project_id}\033[0m")
    print(f"   Diretório de estado: {state_dir}")
    print(f"   Arquivos: {', '.join(f.name for f in sorted(files)) or '(vazio)'}")

    # Tentar exibir o repo_path do project.json para o usuário saber o que NÃO será deletado
    project = ckpt.load_project(project_id)
    if project and project.repo_path:
        print(f"   Repositório de código \033[2m(não será removido)\033[0m: {project.repo_path}")

    # Gerar palavra aleatória de confirmação
    word = random.choice(_CONFIRM_WORDS)
    confirm_phrase = f"{project_id} {word}"

    print(f"\nPara confirmar, digite exatamente: \033[1m{confirm_phrase}\033[0m")
    print("(Ctrl+C para cancelar)\n")

    try:
        answer = input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado.")
        sys.exit(0)

    if answer != confirm_phrase:
        print(f"\n\033[0;31m✗ Confirmação incorreta. Nenhum arquivo foi removido.\033[0m")
        sys.exit(1)

    shutil.rmtree(state_dir)
    print(f"\n\033[0;32m✓ Projeto '{project_id}' removido.\033[0m")


def main():
    # Detecção de subcomando: se o primeiro arg for 'rm', despacha para cmd_remove.
    # Caso contrário, comportamento original (run) para manter compatibilidade.
    if len(sys.argv) >= 2 and sys.argv[1] == "rm":
        if len(sys.argv) < 3:
            print("Uso: squire rm <project-id>")
            sys.exit(1)
        cmd_remove(sys.argv[2])
        return

    parser = argparse.ArgumentParser(description="Orquestrador Claude Code + LLM Local")
    parser.add_argument("project_id", help="ID do projeto (nome do diretório)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem executar")
    parser.add_argument("--resume", action="store_true", help="Retoma sessão anterior")
    parser.add_argument("--quiet", action="store_true", help="Suprime preview de prompts/respostas")
    args = parser.parse_args()

    squire = Squire(
        project_id=args.project_id,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )
    squire.run()


if __name__ == "__main__":
    main()
