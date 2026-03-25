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
    python orchestrator.py <project-id>
    python orchestrator.py <project-id> --resume   # retoma de crash
    python orchestrator.py <project-id> --dry-run   # mostra o que faria
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

import checkpoint as ckpt
import config
from inner_loop import InnerLoop
from homologator import Homologator, TechnicalEscalation
from rate_limiter import RateLimiter
from models import (
    Actor,
    AlertSeverity,
    Checkpoint,
    CursorStep,
    Cursor,
    EventType,
    HistoryEvent,
    ProjectStatus,
    TaskStatus,
)


def log(msg: str, level: str = "info") -> None:
    """Log simples com timestamp."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    prefix = {"info": "→", "ok": "✓", "warn": "⚠", "error": "✗"}
    print(f"[{ts}] {prefix.get(level, '→')} {msg}")


class Orchestrator:
    """Loop principal do orquestrador."""

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

        # Heartbeat thread
        self._heartbeat_stop = threading.Event()

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

    # ── Limpeza de estado git pré-task ────────────────────────────

    def _cleanup_git_state(self) -> None:
        """
        Garante que o working tree do projeto está limpo antes de rodar o aider.
        Se houver arquivos sujos (modified, staged, deleted), executa git checkout -- .
        para restaurar o estado do último commit.
        """
        import subprocess
        repo = self.project.repo_path
        try:
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo, capture_output=True, text=True, timeout=10,
            )
            if status.returncode != 0:
                log(f"git status falhou em {repo} — pulando limpeza", "warn")
                return
            dirty = status.stdout.strip()
            if not dirty:
                return  # working tree limpo, nada a fazer
            log(f"Git state sujo detectado ({len(dirty.splitlines())} arquivo(s)) — limpando", "warn")
            cleanup = subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=repo, capture_output=True, text=True, timeout=10,
            )
            if cleanup.returncode == 0:
                log("Working tree restaurado para HEAD", "ok")
            else:
                log(f"Falha ao limpar git: {cleanup.stderr[:100]}", "warn")
        except Exception as e:
            log(f"Erro ao verificar git state: {e}", "warn")

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
                      actor: Actor = Actor.orchestrator):
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
        if not self.rate_limiter.can_call():
            log("Rate limit ativo — não é possível escalar agora", "warn")
            return context_feedback

        log("Loop detectado — escalação forçada ao Claude Code", "warn")
        self.rate_limiter.record_call()
        self.stats.daily_claude_code_calls += 1
        extra = self.escalation.unblock(task, self.cp.llm_context)
        task.claude_code_assisted = True
        if extra:
            log("Instruções de desbloqueio recebidas do Claude Code", "ok")
        return extra or context_feedback

    # ── Inner Loop (uma task) ──────────────────────────────────────

    def _run_inner_loop(self, task, homologation_feedback: str = "") -> bool:
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
            )

            # Atualizar contexto no checkpoint
            if result.context_summary:
                self.cp.llm_context = result.context_summary

            # Atualizar stats
            self.stats.daily_local_llm_calls += 1
            if self.project_id not in self.stats.projects_touched_today:
                self.stats.projects_touched_today.append(self.project_id)

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

                if self.rate_limiter.can_call():
                    self.rate_limiter.record_call()
                    self.stats.daily_claude_code_calls += 1
                    extra_instructions = self.escalation.unblock(
                        task, self.cp.llm_context,
                    )
                    task.claude_code_assisted = True
                    if extra_instructions:
                        log("Recebeu orientação do Claude Code", "ok")

        # Esgotou tentativas
        log(f"Inner loop esgotou {task.max_attempts} tentativas", "error")
        return False

    # ── Espera produtiva ───────────────────────────────────────────

    def _wait_productively(self, task, last_feedback: str) -> None:
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
            self._run_inner_loop(task, homologation_feedback=last_feedback)

    # ── Ciclo de rodadas (Ralph Loop) ─────────────────────────────

    def _run_homologation(self, task) -> bool:
        """
        Executa o ciclo completo de rodadas para uma task.

        Cada rodada = inner loop (até max_attempts) + homologação pelo Claude Code.
        O inner loop roda sempre, independente de os testes passarem ou não.
        Se aprovado em qualquer rodada → True. Se esgotou max_homologation_attempts → False.
        """
        last_feedback = ""  # feedback acumulado da última rejeição

        while task.homologation_attempt < task.max_homologation_attempts:
            rodada = task.homologation_attempt + 1
            total  = task.max_homologation_attempts

            # ── Inner loop desta rodada ──
            log(f"Rodada {rodada}/{total} — inner loop: [{task.id}] {task.title}")
            task.attempts = 0
            self._run_inner_loop(task, homologation_feedback=last_feedback)
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
                    "Auto-aprovado: skip_homologation=True", Actor.orchestrator,
                )
                task.homologation_result = "approved"
                return True

            if self.dry_run:
                log("[dry-run] Simulando homologação", "warn")
                return True

            # Se rate limited, refina com inner loop enquanto aguarda
            self._wait_productively(task, last_feedback)

            self.rate_limiter.record_call()
            self.stats.daily_claude_code_calls += 1

            result = self.homologator.review(
                task=task,
                context=self.cp.llm_context,
                attempt=task.homologation_attempt,
            )

            self._save_state()

            if result.error:
                log(f"Erro na homologação: {result.error}", "error")
                self._record_event(
                    EventType.homologation_failed, task.id,
                    task.homologation_attempt,
                    f"Erro: {result.error}", Actor.claude_code,
                )
                continue

            verdict_log = result.summary or result.feedback[:100]

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

            # Penúltima rodada com loop persistente: Claude Code implementa diretamente
            is_penultimate = task.homologation_attempt >= task.max_homologation_attempts - 1
            if is_penultimate and self._is_looping(task) and not self.dry_run:
                log(
                    "Penúltima rodada + loop persistente → "
                    "Claude Code implementa diretamente", "warn"
                )
                if self.rate_limiter.can_call():
                    self.rate_limiter.record_call()
                    self.stats.daily_claude_code_calls += 1
                    files_written = self.escalation.implement_directly(
                        task, self.cp.llm_context,
                        rejection_context="\n".join(task.rejection_summaries[-5:]),
                    )
                    if files_written:
                        log(
                            f"Claude Code escreveu {len(files_written)} arquivo(s) — "
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
        if not ckpt.acquire_lock(self.session_id):
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

                # Garantir working tree limpo antes do aider
                self._cleanup_git_state()

                # ── Ciclo de rodadas: inner loop + homologação ──
                homolog_ok = self._run_homologation(task)

                if homolog_ok:
                    task.status = TaskStatus.completed
                    task.completed_at = datetime.now(timezone.utc)
                    self.stats.tasks_completed_today += 1
                    self._record_event(
                        EventType.task_completed, task.id,
                        summary=f"Aprovada na homologação #{task.homologation_attempt}",
                    )
                    log(f"Task concluída: [{task.id}] {task.title}", "ok")
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

        log(f"\n{'─'*50}")
        log(f"Resumo: {completed}/{total} tasks concluídas, {blocked} bloqueadas")
        log(f"Chamadas LLM local: {self.stats.daily_local_llm_calls}")
        log(f"Chamadas Claude Code: {self.stats.daily_claude_code_calls}")
        ratio = (
            self.stats.daily_local_llm_calls / max(1, self.stats.daily_claude_code_calls)
        )
        log(f"Proporção local/Claude: {ratio:.1f}:1 (meta: 30:1)")
        log(f"{'─'*50}")


# ── Entrypoint ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Orquestrador Claude Code + LLM Local")
    parser.add_argument("project_id", help="ID do projeto (nome do diretório)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem executar")
    parser.add_argument("--resume", action="store_true", help="Retoma sessão anterior")
    parser.add_argument("--quiet", action="store_true", help="Suprime preview de prompts/respostas")
    args = parser.parse_args()

    orchestrator = Orchestrator(
        project_id=args.project_id,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )
    orchestrator.run()


if __name__ == "__main__":
    main()
