#!/usr/bin/env python3
"""
Correção dirigida de uma task bloqueada.
Invocado por 'squire fix <projeto> <task-id> [--yes]'.

Ciclo completo: Claude Code implementa a correção diretamente (usando o
histórico de rejeições como contexto), os testes do projeto rodam, e UMA
rodada de homologação decide — aprovada vira completed + commit; rejeitada
permanece blocked com o novo veredito gravado no homologation_log.json.

Segura o session lock durante todo o ciclo (mexe no repo e no tasks.json).
Não usa rate limiter (ação manual, ~2-3 chamadas), mas todo custo é
contabilizado no global-stats.json.

Exit codes:
  0 aprovada · 1 não encontrado · 2 task não está blocked · 3 lock ativo
  4 implement não escreveu arquivos · 5 erro de infra na homologação
  6 rejeitada (ciclo rodou; veredito negativo)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import checkpoint as ckpt
import config
from homologator import Homologator, HomologationResult, TechnicalEscalation
from inner_loop import InnerLoop
from models import (
    Actor, EventType, HistoryEvent, HomologationLogEntry, LLMContextSummary,
    ProjectStatus, Task, TaskStatus, TokenUsage,
)

# ── Cores ──────────────────────────────────────────────────────────

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _log(msg: str, kind: str = "info") -> None:
    icon = {"info": f"{CYAN}→{RESET}", "ok": f"{GREEN}✓{RESET}",
            "warn": f"{YELLOW}⚠{RESET}", "error": f"{RED}✗{RESET}"}[kind]
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {icon} {msg}", flush=True)


# ── Contexto de rejeições ──────────────────────────────────────────

_TEST_GUARD = (
    "\n\nREGRA INEGOCIÁVEL: É PROIBIDO modificar arquivos de teste "
    "(test_*.py, *.test.ts, *_test.go etc.) — eles estão protegidos por hash "
    "e qualquer alteração será revertida automaticamente. Implemente apenas "
    "o código de produção que faz os testes passarem."
)


def build_rejection_context(project_id: str, task: Task) -> str:
    """Últimos vereditos completos do log; fallback para rejection_summaries."""
    log = ckpt.load_homologation_log(project_id)
    entries = [e for e in log.entries if e.task_id == task.id and not e.approved]
    if entries:
        parts = []
        for e in entries[-3:]:
            block = [f"Rodada {e.attempt}: {e.summary}"]
            if e.fix_suggestion:
                block.append(f"Como corrigir: {e.fix_suggestion}")
            if e.feedback:
                block.append(f"Detalhes: {e.feedback}")
            parts.append("\n".join(block))
        return "\n\n---\n\n".join(parts) + _TEST_GUARD
    if task.rejection_summaries:
        return (
            "Rejeições anteriores (resumos):\n- "
            + "\n- ".join(task.rejection_summaries[-5:])
            + _TEST_GUARD
        )
    return "(sem histórico de rejeições registrado)" + _TEST_GUARD


# ── Contabilidade ──────────────────────────────────────────────────

def account_usage(usage: Optional[TokenUsage], task: Task) -> float:
    """Versão standalone do Squire._account_call para o ciclo de fix."""
    stats = ckpt.load_stats()
    stats.daily_claude_code_calls += 1
    cost = 0.0
    if usage is not None:
        cost = max(0.0, float(usage.cost_usd or 0.0))
        stats.cost_estimate_usd += cost
        stats.daily_tokens += int(usage.prompt_tokens or 0) + int(usage.completion_tokens or 0)
        if usage.tokens_unknown:
            stats.daily_calls_unknown_cost += 1
        if usage.model:
            stats.cost_by_model[usage.model] = (
                stats.cost_by_model.get(usage.model, 0.0) + cost
            )
        task.cost_usd = float(task.cost_usd or 0.0) + cost
    else:
        stats.daily_calls_unknown_cost += 1
    ckpt.save_stats(stats)
    return cost


# ── Git ────────────────────────────────────────────────────────────

def commit_fix(repo_path: str, task: Task) -> None:
    """Commita o resultado aprovado (versão guarded do _commit_task_completion)."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if status.returncode != 0 or not status.stdout.strip():
            return
        subprocess.run(["git", "add", "-A"], cwd=repo_path, capture_output=True, timeout=15)
        msg = f"fix: [{task.id}] {task.title[:60]}"
        commit = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
        if commit.returncode == 0:
            _log(f"Commitado: {msg}", "ok")
        elif "nothing to commit" not in commit.stdout + commit.stderr:
            _log(f"Falha ao commitar: {commit.stderr[:120]}", "warn")
    except Exception as e:
        _log(f"Erro no commit: {e}", "warn")


def recompute_project_status(project_id: str) -> None:
    """Sem tasks bloqueadas restantes → projeto sai de 'blocked'."""
    project = ckpt.load_project(project_id)
    if project is None:
        return
    tasks = ckpt.load_tasks(project_id).tasks
    blocked = any(t.status == TaskStatus.blocked for t in tasks)
    if blocked:
        return
    all_done = all(t.status == TaskStatus.completed for t in tasks)
    new_status = ProjectStatus.completed if all_done else ProjectStatus.implementing
    if project.status != new_status:
        project.status = new_status
        project.updated_at = datetime.now(timezone.utc)
        ckpt.save_project(project_id, project)
        _log(f"Status do projeto → {new_status.value}", "ok")


def _append_log_entry(project_id: str, task: Task, result: HomologationResult) -> None:
    ckpt.append_homologation_entry(project_id, HomologationLogEntry(
        task_id=task.id,
        attempt=task.homologation_attempt,
        approved=result.approved,
        summary=result.summary or "",
        feedback=result.feedback or "",
        fix_suggestion=result.fix_suggestion or "",
        suggestions=result.suggestions or [],
        source="fix",
        cost_usd=result.usage.cost_usd if result.usage else 0.0,
        model=(result.usage.model or None) if result.usage else None,
    ))


def _record_event(project_id: str, type_: EventType, task: Task, summary: str) -> None:
    ckpt.append_event(project_id, HistoryEvent(
        timestamp=datetime.now(timezone.utc),
        type=type_, task_id=task.id,
        attempt=task.homologation_attempt,
        summary=summary[:300], actor=Actor.claude_code,
    ))


# ── Ciclo principal ────────────────────────────────────────────────

def run_fix(project_id: str, task_id: str) -> int:
    project = ckpt.load_project(project_id)
    if project is None:
        _log(f"Projeto '{project_id}' não encontrado.", "error")
        return 1
    task_list = ckpt.load_tasks(project_id)
    task = next((t for t in task_list.tasks if t.id == task_id), None)
    if task is None:
        _log(f"Task '{task_id}' não encontrada.", "error")
        return 1
    if task.status != TaskStatus.blocked:
        _log(f"Task '{task_id}' está '{task.status.value}' — só tasks blocked podem ser corrigidas.", "error")
        return 2

    session_id = f"fix-{project_id}-{task_id}-{os.getpid()}"
    if not ckpt.acquire_lock(session_id, project_id):
        _log("Sessão squire ativa — aguarde terminar ou use 'squire kill'.", "error")
        return 3

    started = time.monotonic()
    try:
        _log(f"Corrigindo [{task.id}] {task.title}")
        rejection_context = build_rejection_context(project_id, task)

        # Proteção de testes: snapshot antes, revert depois
        il = InnerLoop(project.repo_path, verbose=True)
        test_hashes = il.snapshot_test_hashes()

        # 1) Claude implementa diretamente
        esc = TechnicalEscalation(project.repo_path)
        context = _build_context(project_id, task)
        _log("Claude Code implementando a correção…")
        files_written, usage = esc.implement_directly(
            task, context, rejection_context=rejection_context
        )
        cost1 = account_usage(usage, task)
        if not files_written:
            ckpt.save_tasks(project_id, task_list)  # persiste cost_usd
            _log("Claude não escreveu nenhum arquivo — abortando.", "error")
            return 4
        _log(f"{len(files_written)} arquivo(s) escritos (${cost1:.3f})", "ok")

        # 2) Reverter qualquer violação de testes
        modified_tests = il.check_test_integrity(test_hashes)
        if modified_tests:
            il.revert_test_files(modified_tests)
            _log(f"{len(modified_tests)} arquivo(s) de teste alterados — revertidos", "warn")

        # 3) Testes
        results = il.run_tests()
        context.tests_passing = results.get("passing", 0)
        context.tests_failing = results.get("failing", 0)
        context.test_summary = (results.get("output") or "")[-1500:]
        kind = "ok" if results.get("success") else "warn"
        _log(f"Testes: {context.tests_passing} ok / {context.tests_failing} falhando", kind)

        # 4) UMA rodada de homologação (com 1 retry de infra, se houver tempo)
        hom = Homologator(project.repo_path)
        result = None
        for attempt in range(2):
            result = hom.review(
                task=task, context=context,
                attempt=task.homologation_attempt + 1,
                test_hashes=test_hashes or None,
            )
            account_usage(result.usage, task)
            elapsed = time.monotonic() - started
            if (
                result.error
                and result.error_kind == "infra"
                and attempt == 0
                and elapsed < 8 * 60  # sem retry quando já estamos longos
            ):
                _log(f"Falha de infra no review ({result.error}) — retry 1/1", "warn")
                time.sleep(10)
                continue
            break

        if result.error:
            ckpt.save_tasks(project_id, task_list)
            _log(f"Homologação falhou por infra/config: {result.error}", "error")
            return 5

        task.homologation_attempt += 1
        _append_log_entry(project_id, task, result)

        if result.approved:
            task.status = TaskStatus.completed
            task.homologation_result = "approved"
            task.completed_at = datetime.now(timezone.utc)
            task.claude_code_assisted = True
            ckpt.save_tasks(project_id, task_list)
            _record_event(
                project_id, EventType.homologation_approved, task,
                f"[fix] {result.summary or result.feedback[:200]}",
            )
            commit_fix(project.repo_path, task)
            recompute_project_status(project_id)
            _log(f"Task aprovada e concluída! {result.summary[:120]}", "ok")
            _log(f"Custo total da task: ${task.cost_usd:.3f}")
            return 0

        # Rejeitada: permanece blocked, veredito novo disponível para triagem
        if result.summary:
            task.rejection_summaries.append(result.summary)
            task.rejection_summaries = task.rejection_summaries[-10:]
        ckpt.save_tasks(project_id, task_list)
        _record_event(
            project_id, EventType.homologation_failed, task,
            f"[fix] {result.summary or result.feedback[:200]}",
        )
        _log(f"Correção rejeitada na homologação: {result.summary[:160]}", "error")
        _log("A task permanece bloqueada — veredito completo no homologation_log.json.")
        return 6
    finally:
        ckpt.release_lock()


def _build_context(project_id: str, task: Task) -> LLMContextSummary:
    """Reaproveita o contexto do checkpoint quando ele aponta para esta task."""
    cp = ckpt.load_checkpoint(project_id)
    if cp is not None and cp.cursor.current_task_id == task.id:
        return cp.llm_context
    return LLMContextSummary(last_instruction=task.description or task.title)


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    args = [a for a in sys.argv[1:] if a != "--yes"]
    if len(args) < 2 or any(a in ("-h", "--help", "help") for a in args):
        print(f"""
{BOLD}squire fix{RESET} — Claude corrige uma task bloqueada (ciclo completo)

  {CYAN}squire fix{RESET} <projeto> <task-id>

Fluxo: implementação direta pelo Claude (com o histórico de rejeições
como contexto) → testes → 1 rodada de homologação → aprovada = completed
+ commit; rejeitada = permanece blocked com o veredito no log.

Exit codes: 0 aprovada · 2 não-blocked · 3 lock ativo · 4 sem arquivos ·
5 infra · 6 rejeitada
""")
        sys.exit(0 if any(a in ("-h", "--help", "help") for a in sys.argv[1:]) else 1)
    sys.exit(run_fix(args[0], args[1]))


if __name__ == "__main__":
    main()
