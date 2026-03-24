"""
Gerenciador de checkpoint — leitura/escrita atômica de estado no filesystem.

Toda escrita usa o padrão write-to-temp-then-rename para garantir que
um crash no meio da operação não corrompe o JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TypeVar

from pydantic import BaseModel

from models import (
    Alert, AlertList, AlertSeverity, Checkpoint, GlobalStats,
    History, HistoryEvent, Project, SessionLock, TaskList,
)
import config

T = TypeVar("T", bound=BaseModel)


# ── Escrita Atômica ────────────────────────────────────────────────

def atomic_write_json(path: Path, data: dict) -> None:
    """Escreve JSON de forma atômica via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def save_model(path: Path, model: BaseModel) -> None:
    """Serializa um modelo Pydantic e salva atomicamente."""
    atomic_write_json(path, model.model_dump(mode="json"))


def load_model(path: Path, model_class: type[T]) -> Optional[T]:
    """Carrega um modelo Pydantic do filesystem. Retorna None se não existir."""
    if not path.exists():
        return None
    with open(path) as f:
        return model_class.model_validate_json(f.read())


# ── Checkpoint ─────────────────────────────────────────────────────

def checkpoint_path(project_id: str) -> Path:
    return config.project_dir(project_id) / "checkpoint.json"


def load_checkpoint(project_id: str) -> Optional[Checkpoint]:
    return load_model(checkpoint_path(project_id), Checkpoint)


def save_checkpoint(project_id: str, cp: Checkpoint) -> None:
    cp.last_heartbeat = datetime.utcnow()
    save_model(checkpoint_path(project_id), cp)


def heartbeat(project_id: str, cp: Checkpoint) -> None:
    """Atualiza apenas o heartbeat — operação leve para o timer."""
    cp.last_heartbeat = datetime.utcnow()
    save_checkpoint(project_id, cp)


# ── Project State ──────────────────────────────────────────────────

def load_project(project_id: str) -> Optional[Project]:
    return load_model(config.project_dir(project_id) / "project.json", Project)


def save_project(project_id: str, project: Project) -> None:
    project.updated_at = datetime.utcnow()
    save_model(config.project_dir(project_id) / "project.json", project)


def load_tasks(project_id: str) -> TaskList:
    result = load_model(config.project_dir(project_id) / "tasks.json", TaskList)
    return result or TaskList()


def save_tasks(project_id: str, tasks: TaskList) -> None:
    save_model(config.project_dir(project_id) / "tasks.json", tasks)


def load_history(project_id: str) -> History:
    result = load_model(config.project_dir(project_id) / "history.json", History)
    return result or History()


def save_history(project_id: str, history: History) -> None:
    save_model(config.project_dir(project_id) / "history.json", history)


def append_event(project_id: str, event: HistoryEvent) -> None:
    """Adiciona um evento ao histórico e salva."""
    history = load_history(project_id)
    history.append(event)
    save_history(project_id, history)


# ── Session Lock ───────────────────────────────────────────────────

def acquire_lock(session_id: str) -> bool:
    """Tenta adquirir o lock. Retorna True se conseguiu."""
    existing = load_model(config.SESSION_LOCK_FILE, SessionLock)

    if existing is not None:
        # Lock existe — checar se expirou
        expires_at = existing.acquired_at + timedelta(
            minutes=existing.ttl_minutes
        )
        if datetime.utcnow() < expires_at:
            # Lock ainda válido e de outra sessão
            if existing.holder != session_id:
                return False
            # Mesma sessão — renovar
        # Lock expirado — pode tomar

    lock = SessionLock(
        holder=session_id,
        acquired_at=datetime.utcnow(),
        ttl_minutes=config.SESSION_LOCK_TTL_MINUTES,
        pid=os.getpid(),
    )
    save_model(config.SESSION_LOCK_FILE, lock)
    return True


def release_lock() -> None:
    """Libera o lock."""
    if config.SESSION_LOCK_FILE.exists():
        config.SESSION_LOCK_FILE.unlink()


def renew_lock(session_id: str) -> None:
    """Renova o TTL do lock."""
    existing = load_model(config.SESSION_LOCK_FILE, SessionLock)
    if existing and existing.holder == session_id:
        existing.acquired_at = datetime.utcnow()
        save_model(config.SESSION_LOCK_FILE, existing)


# ── Alerts ─────────────────────────────────────────────────────────

def load_alerts() -> AlertList:
    result = load_model(config.ALERTS_FILE, AlertList)
    return result or AlertList()


def add_alert(
    project_id: str,
    alert_type: str,
    message: str,
    task_id: Optional[str] = None,
    severity: AlertSeverity = AlertSeverity.critical,
) -> None:
    """Adiciona alerta e persiste."""
    alerts = load_alerts()
    alerts.alerts.append(Alert(
        project_id=project_id,
        severity=severity,
        type=alert_type,
        task_id=task_id,
        message=message,
    ))
    save_model(config.ALERTS_FILE, alerts)


# ── Global Stats ───────────────────────────────────────────────────

def load_stats() -> GlobalStats:
    result = load_model(config.STATS_FILE, GlobalStats)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if result is None or result.date != today:
        return GlobalStats(date=today)
    return result


def save_stats(stats: GlobalStats) -> None:
    save_model(config.STATS_FILE, stats)
