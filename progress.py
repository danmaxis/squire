"""
Geração de progress.txt a partir do history.json.

O progress.txt serve como memória de longo prazo para o LLM local:
cada task concluída contribui com uma linha de lição aprendida,
permitindo que iterações futuras saltem a fase de descoberta.

Inspirado no padrão Ralph Loop (Geoffrey Huntley).
"""

from __future__ import annotations

from pathlib import Path

import checkpoint as ckpt
import config
from models import EventType, TaskStatus


def generate_progress(project_id: str) -> None:
    """
    Lê history.json e tasks.json do projeto e gera/atualiza progress.txt
    no diretório de estado do projeto.

    Formato do progress.txt:
        [task-001] Título da task
          Tentativas: 3 | Último erro antes de passar: AssertionError: ...
          Lição: passou após corrigir importação circular em models.py

    Chamado pelo squire após cada task concluída.
    """
    history = ckpt.load_history(project_id)
    task_list = ckpt.load_tasks(project_id)

    if not history or not task_list:
        return

    tasks_by_id = {t.id: t for t in task_list.tasks}
    lines: list[str] = [
        "# progress.txt — memória acumulada de iterações",
        "# Gerado automaticamente pelo squire. Não editar manualmente.",
        "",
    ]

    # Agrupar eventos por task_id
    events_by_task: dict[str, list] = {}
    for event in history.events:
        if event.task_id:
            events_by_task.setdefault(event.task_id, []).append(event)

    for task_id, events in events_by_task.items():
        task = tasks_by_id.get(task_id)
        if not task or task.status != TaskStatus.completed:
            continue

        # Contar tentativas de implementação
        impl_attempts = sum(
            1 for e in events
            if e.type == EventType.implementation_cycle
        )

        # Último erro antes do teste passar
        last_error: str | None = None
        for e in reversed(events):
            if e.type == EventType.tests_failed and e.summary:
                last_error = e.summary[:200]
                break

        # Número de rejeições de homologação
        rejections = sum(
            1 for e in events
            if e.type == EventType.homologation_failed
        )

        lines.append(f"[{task_id}] {task.title}")
        lines.append(f"  Tentativas: {impl_attempts} | Rejeições: {rejections}")
        if last_error:
            lines.append(f"  Último erro: {last_error}")
        if task.rejection_summaries:
            lines.append(f"  Feedbacks de homologação: {'; '.join(task.rejection_summaries[-2:])}")
        lines.append("")

    progress_path = config.project_dir(project_id) / "progress.txt"
    progress_path.write_text("\n".join(lines), encoding="utf-8")


def load_progress(project_id: str) -> str:
    """
    Lê progress.txt do projeto e retorna como string.
    Retorna string vazia se não existir.
    """
    progress_path = config.project_dir(project_id) / "progress.txt"
    if not progress_path.exists():
        return ""
    return progress_path.read_text(encoding="utf-8")
