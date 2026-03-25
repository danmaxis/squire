"""
Schemas Pydantic para os JSONs do orquestrador.
Servem como contrato entre orquestrador, inner loop e dashboard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────

class ProjectStatus(str, Enum):
    planning = "planning"
    implementing = "implementing"
    reviewing = "reviewing"
    blocked = "blocked"
    completed = "completed"


class TaskStatus(str, Enum):
    pending = "pending"
    implementing = "implementing"
    testing = "testing"
    homologating = "homologating"
    completed = "completed"
    blocked = "blocked"


class CursorStep(str, Enum):
    planning = "planning"
    llm_execution = "llm_execution"
    testing = "testing"
    homologation = "homologation"
    completed = "completed"


class EventType(str, Enum):
    task_started = "task_started"
    implementation_cycle = "implementation_cycle"
    tests_passed = "tests_passed"
    tests_failed = "tests_failed"
    homologation_requested = "homologation_requested"
    homologation_approved = "homologation_approved"
    homologation_failed = "homologation_failed"
    escalation_created = "escalation_created"
    task_completed = "task_completed"
    session_started = "session_started"
    session_resumed = "session_resumed"
    session_ended = "session_ended"


class AlertSeverity(str, Enum):
    warning = "warning"
    critical = "critical"


class Actor(str, Enum):
    local_llm = "local_llm"
    claude_code = "claude_code"
    orchestrator = "orchestrator"
    human = "human"


# ── Project ────────────────────────────────────────────────────────

class Project(BaseModel):
    id: str
    name: str
    description: str
    repo_path: str
    stack: list[str] = []
    status: ProjectStatus = ProjectStatus.planning
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_task_id: Optional[str] = None
    coding_backend: Optional[str] = None  # None = usa ORCH_CODING_BACKEND global


# ── Tasks ──────────────────────────────────────────────────────────

class Subtask(BaseModel):
    id: str
    title: str
    status: TaskStatus = TaskStatus.pending


class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.pending
    assigned_to: Actor = Actor.local_llm
    attempts: int = 0
    max_attempts: int = 10  # inner loop retries
    homologation_result: Optional[str] = None  # "approved" | "rejected"
    homologation_attempt: int = 0
    max_homologation_attempts: int = 5  # número máximo de rodadas (inner loop + homologação)
    completed_at: Optional[datetime] = None
    claude_code_assisted: bool = False
    subtasks: list[Subtask] = []


class TaskList(BaseModel):
    tasks: list[Task] = []


# ── History ────────────────────────────────────────────────────────

class HistoryEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType
    task_id: Optional[str] = None
    attempt: Optional[int] = None
    summary: str = ""
    actor: Actor = Actor.orchestrator


class History(BaseModel):
    events: list[HistoryEvent] = []

    def append(self, event: HistoryEvent):
        self.events.append(event)


# ── Commits ────────────────────────────────────────────────────────

class CommitSummary(BaseModel):
    sha: str
    message: str
    timestamp: datetime
    diff_summary: str = ""  # gerado pelo LLM
    files_changed: list[str] = []


class CommitLog(BaseModel):
    commits: list[CommitSummary] = []


# ── Checkpoint ─────────────────────────────────────────────────────

class Cursor(BaseModel):
    current_task_id: Optional[str] = None
    current_subtask_id: Optional[str] = None
    step: CursorStep = CursorStep.planning
    attempt: int = 0
    homologation_attempt: int = 0


class LLMContextSummary(BaseModel):
    """Resumo compacto do contexto — não é o histórico completo,
    mas o suficiente para o Claude Code reconstruir um prompt de retomada."""
    last_instruction: str = ""
    files_touched: list[str] = []
    last_error: Optional[str] = None
    tests_passing: int = 0
    tests_failing: int = 0
    test_summary: str = ""


class RateLimitState(BaseModel):
    claude_code_calls_this_window: int = 0
    window_started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_duration_minutes: int = 30
    max_calls_per_window: int = 10


class RecoveryHints(BaseModel):
    can_resume: bool = True
    resume_action: str = "continue"  # continue | retry_current_subtask | skip_task
    blocked_reason: Optional[str] = None
    escalation_needed: bool = False


class Checkpoint(BaseModel):
    version: int = 1
    session_id: str = ""
    phase: ProjectStatus = ProjectStatus.implementing
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cursor: Cursor = Field(default_factory=Cursor)
    llm_context: LLMContextSummary = Field(default_factory=LLMContextSummary)
    rate_limit: RateLimitState = Field(default_factory=RateLimitState)
    recovery: RecoveryHints = Field(default_factory=RecoveryHints)


# ── Session Lock ───────────────────────────────────────────────────

class SessionLock(BaseModel):
    holder: str
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_minutes: int = 60
    pid: int = 0


# ── Alerts ─────────────────────────────────────────────────────────

class Alert(BaseModel):
    project_id: str
    severity: AlertSeverity
    type: str
    task_id: Optional[str] = None
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False


class AlertList(BaseModel):
    alerts: list[Alert] = []


# ── Global Stats ───────────────────────────────────────────────────

class GlobalStats(BaseModel):
    daily_claude_code_calls: int = 0
    daily_local_llm_calls: int = 0
    date: str = ""  # YYYY-MM-DD
    cost_estimate_usd: float = 0.0
    projects_touched_today: list[str] = []
    tasks_completed_today: int = 0
    approval_first_try_rate: float = 0.0  # % aprovadas na 1ª homologação
