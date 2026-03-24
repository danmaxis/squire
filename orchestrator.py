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
import uuid
from datetime import datetime

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
    ts = datetime.utcnow().strftime("%H:%M:%S")
    prefix = {"info": "→", "ok": "✓", "warn": "⚠", "error": "✗"}
    print(f"[{ts}] {prefix.get(level, '→')} {msg}")


class Orchestrator:
    """Loop principal do orquestrador."""

    def __init__(self, project_id: str, dry_run: bool = False):
        self.project_id = project_id
        self.dry_run = dry_run
        self.session_id = f"sess-{datetime.utcnow():%Y%m%d-%H%M}-{uuid.uuid4().hex[:6]}"

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
        self.inner_loop = InnerLoop(self.project.repo_path)
        self.homologator = Homologator(self.project.repo_path)
        self.escalation = TechnicalEscalation(self.project.repo_path)
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

    # ── Inner Loop (uma task) ──────────────────────────────────────

    def _run_inner_loop(self, task) -> bool:
        """
        Executa o inner loop até os testes passarem ou esgotar tentativas.
        Retorna True se os testes passaram.
        """
        extra_instructions = ""

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

            if result.success:
                log(f"Testes passando ({result.tests_passing} ok)", "ok")
                self._record_event(
                    EventType.tests_passed, task.id, task.attempts,
                    f"{result.tests_passing} testes passando",
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

    # ── Homologação (uma task) ─────────────────────────────────────

    def _run_homologation(self, task) -> bool:
        """
        Submete a task para homologação pelo Claude Code.
        Retorna True se aprovada.
        """
        while task.homologation_attempt < task.max_homologation_attempts:
            task.homologation_attempt += 1
            task.status = TaskStatus.homologating
            self.cp.cursor.step = CursorStep.homologation
            self.cp.cursor.homologation_attempt = task.homologation_attempt

            log(
                f"Homologação: {task.title} "
                f"(tentativa {task.homologation_attempt}/{task.max_homologation_attempts})"
            )

            if self.dry_run:
                log("[dry-run] Simulando homologação", "warn")
                return True

            # Rate limit (só no modo real)
            self.rate_limiter.wait_if_needed()
            if not self.rate_limiter.can_call():
                log("Rate limit atingido, aguardando...", "warn")
                self.rate_limiter.wait_if_needed()

            self.rate_limiter.record_call()
            self.stats.daily_claude_code_calls += 1

            result = self.homologator.review(
                task=task,
                context=self.cp.llm_context,
                attempt=task.homologation_attempt,
            )

            # Checkpoint
            self._save_state()

            if result.error:
                log(f"Erro na homologação: {result.error}", "error")
                self._record_event(
                    EventType.homologation_failed, task.id,
                    task.homologation_attempt,
                    f"Erro: {result.error}", Actor.claude_code,
                )
                continue

            if result.approved:
                log(f"Homologação aprovada! {result.feedback[:100]}", "ok")
                self._record_event(
                    EventType.homologation_approved, task.id,
                    task.homologation_attempt,
                    result.feedback[:300], Actor.claude_code,
                )
                task.homologation_result = "approved"
                return True

            # Rejeitado — feedback volta pro inner loop
            log(f"Homologação rejeitada: {result.feedback[:100]}", "warn")
            self._record_event(
                EventType.homologation_failed, task.id,
                task.homologation_attempt,
                result.feedback[:300], Actor.claude_code,
            )

            # Se ainda tem tentativas, roda inner loop de novo com o feedback
            if task.homologation_attempt < task.max_homologation_attempts:
                log("Voltando ao inner loop com feedback da homologação...")
                task.attempts = 0  # reset do inner loop
                inner_ok = self._run_inner_loop(task)
                if not inner_ok:
                    # Inner loop falhou de novo — pular homologação
                    continue

        # Esgotou homologações
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
                log(f"Task: {task.title}")
                log(f"{'='*50}")

                self._record_event(
                    EventType.task_started, task.id,
                    summary=task.title,
                )

                # ── Inner loop ──
                inner_ok = self._run_inner_loop(task)

                if not inner_ok:
                    # Inner loop falhou completamente
                    task.status = TaskStatus.blocked
                    self.cp.recovery.can_resume = True
                    self.cp.recovery.resume_action = "skip_task"
                    self.cp.recovery.blocked_reason = (
                        f"Inner loop esgotou {task.max_attempts} tentativas"
                    )
                    ckpt.add_alert(
                        self.project_id,
                        "inner_loop_exhausted",
                        f"Task '{task.title}' não passou nos testes após "
                        f"{task.max_attempts} tentativas.",
                        task_id=task.id,
                        severity=AlertSeverity.critical,
                    )
                    self._record_event(
                        EventType.escalation_created, task.id,
                        summary="Inner loop esgotado — intervenção necessária",
                    )
                    self._save_state()
                    continue

                # ── Homologação ──
                homolog_ok = self._run_homologation(task)

                if homolog_ok:
                    task.status = TaskStatus.completed
                    task.completed_at = datetime.utcnow()
                    self.stats.tasks_completed_today += 1
                    self._record_event(
                        EventType.task_completed, task.id,
                        summary=f"Aprovada na homologação #{task.homologation_attempt}",
                    )
                    log(f"Task concluída: {task.title}", "ok")
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
    args = parser.parse_args()

    orchestrator = Orchestrator(
        project_id=args.project_id,
        dry_run=args.dry_run,
    )
    orchestrator.run()


if __name__ == "__main__":
    main()
