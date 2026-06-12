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
    red_phase = "red_phase"       # escrita do teste (antes do inner loop)
    llm_execution = "llm_execution"
    testing = "testing"
    homologation = "homologation"
    completed = "completed"


class Effort(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TestAuthor(str, Enum):
    claude = "claude"
    local = "local"


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
    squire = "squire"
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
    # Histórico compacto de rejeições — usado para detectar loops repetitivos
    rejection_summaries: list[str] = []
    # Contador de ciclos consecutivos sem nenhum arquivo modificado
    no_progress_streak: int = 0
    # Se True, pula homologação pelo Claude Code (auto-aprovado após inner loop)
    # Útil para tasks de setup/boilerplate que não precisam de review
    skip_homologation: bool = False
    # Nível de complexidade — usado para selecionar o modelo LLM adequado
    effort: Effort = Effort.medium
    # Se True, exige fase RED (escrita de testes) antes do inner loop
    tdd: bool = True
    # Quem escreve os testes na fase RED
    test_author: TestAuthor = TestAuthor.claude
    # Limite de custo (USD) para esta task — None ou 0 = sem limite por-task
    max_usd: Optional[float] = None
    # Custo acumulado nesta task; reset junto com attempts no `squire reset`
    cost_usd: float = 0.0


class TaskList(BaseModel):
    tasks: list[Task] = []


# ── History ────────────────────────────────────────────────────────

class HistoryEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType
    task_id: Optional[str] = None
    attempt: Optional[int] = None
    summary: str = ""
    actor: Actor = Actor.squire


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
    # Preenchido quando `git log` falha; permite ao dashboard distinguir
    # "projeto sem commits ainda" de "esperava arquivo mas git quebrou".
    error: Optional[str] = None


# ── Homologation log ───────────────────────────────────────────────

class HomologationLogEntry(BaseModel):
    """Veredito completo de uma rodada de homologação.

    Diferente de Task.rejection_summaries (300 chars, usado pela detecção
    de loops), aqui o feedback e o fix_suggestion são preservados na
    íntegra — é o que o dashboard mostra na triagem de tasks bloqueadas
    e o que `squire fix` usa como contexto. Erros de infra não viram
    entrada (não são vereditos).
    """
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: str
    attempt: int = 0
    approved: bool = False
    summary: str = ""
    feedback: str = ""
    fix_suggestion: str = ""
    suggestions: list[str] = []
    source: str = "session"  # "session" (loop do orquestrador) | "fix" (squire fix)
    cost_usd: float = 0.0
    model: Optional[str] = None


class HomologationLog(BaseModel):
    entries: list[HomologationLogEntry] = []


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
    # Budget USD diário (0 = sem limite). Persistido para sobreviver a --resume.
    max_daily_usd: float = 0.0
    daily_cost_usd: float = 0.0
    daily_cost_date: str = ""  # YYYY-MM-DD; reset quando o dia vira


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
    project_id: Optional[str] = None
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
    daily_tokens: int = 0
    # Custo agregado por modelo (ex: {"claude-opus-4-7": 0.42, "journal-synth": 0.0})
    cost_by_model: dict[str, float] = {}
    # Calls cuja usage não foi reportada pelo backend — soma serve de "actual cost likely higher"
    daily_calls_unknown_cost: int = 0
    projects_touched_today: list[str] = []
    tasks_completed_today: int = 0
    # Contadores-base da taxa de aprovação (tasks com skip_homologation não contam)
    tasks_homologated_today: int = 0
    tasks_approved_first_try_today: int = 0
    approval_first_try_rate: float = 0.0  # % aprovadas na 1ª homologação


# ── Command queue (dashboard → agente host) ───────────────────────

class CommandType(str, Enum):
    """Whitelist de comandos que o agente host aceita executar."""
    new_project = "new_project"
    run = "run"
    resume = "resume"
    kill = "kill"
    plan_tasks = "plan_tasks"
    split_task = "split_task"
    fix_task = "fix_task"


class CommandStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class QueuedCommand(BaseModel):
    """Comando enfileirado pelo dashboard em commands/pending/<id>.json."""
    id: str
    type: CommandType
    project_id: Optional[str] = None  # None apenas para kill
    args: dict = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requested_by: str = "dashboard"


class CommandResult(BaseModel):
    """Resultado escrito pelo agente em commands/done/<id>.json."""
    id: str
    type: CommandType
    project_id: Optional[str] = None
    status: CommandStatus
    exit_code: Optional[int] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class TokenUsage(BaseModel):
    """Uso de tokens reportado por um backend após uma chamada.

    `tokens_unknown=True` indica que o backend não expôs uso (ex: OpenCode/Crush CLI)
    — nesse caso o custo é registrado como 0 mas o flag permite que o dashboard
    sinalize "custo real provavelmente maior" em vez de assumir gratuidade.
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0  # cache reads (Claude prompt caching)
    cost_usd: float = 0.0
    model: str = ""
    tokens_unknown: bool = False
