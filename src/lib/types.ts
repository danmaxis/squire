export type ProjectStatus = 'planning' | 'implementing' | 'reviewing' | 'blocked' | 'completed';
export type TaskStatus = 'pending' | 'implementing' | 'testing' | 'homologating' | 'completed' | 'blocked';
export type CursorStep = 'planning' | 'red_phase' | 'llm_execution' | 'testing' | 'homologation' | 'completed';
export type Effort = 'low' | 'medium' | 'high';
export type TestAuthor = 'claude' | 'local';
export type EventType =
  | 'task_started'
  | 'implementation_cycle'
  | 'tests_passed'
  | 'tests_failed'
  | 'homologation_requested'
  | 'homologation_approved'
  | 'homologation_failed'
  | 'escalation_created'
  | 'task_completed'
  | 'session_started'
  | 'session_resumed'
  | 'session_ended';
export type AlertSeverity = 'warning' | 'critical';
export type Actor = 'local_llm' | 'claude_code' | 'squire' | 'human';

export interface Subtask {
  id: string;
  title: string;
  status: TaskStatus;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  assigned_to: Actor;
  attempts: number;
  max_attempts: number;
  homologation_result: string | null;
  homologation_attempt: number;
  max_homologation_attempts: number;
  completed_at: string | null;
  claude_code_assisted: boolean;
  subtasks: Subtask[];
  rejection_summaries: string[];
  no_progress_streak: number;
  skip_homologation: boolean;
  effort: Effort;
  tdd: boolean;
  test_author: TestAuthor;
}

export interface TaskList {
  tasks: Task[];
}

export interface HistoryEvent {
  timestamp: string;
  type: EventType;
  task_id: string | null;
  attempt: number | null;
  summary: string;
  actor: Actor;
}

export interface History {
  events: HistoryEvent[];
}

export interface CommitSummary {
  sha: string;
  message: string;
  timestamp: string;
  diff_summary: string;
  files_changed: string[];
}

export interface CommitLog {
  commits: CommitSummary[];
}

export interface Cursor {
  current_task_id: string | null;
  current_subtask_id: string | null;
  step: CursorStep;
  attempt: number;
  homologation_attempt: number;
}

export interface LLMContextSummary {
  last_instruction: string;
  files_touched: string[];
  last_error: string | null;
  tests_passing: number;
  tests_failing: number;
  test_summary: string;
}

export interface RateLimitState {
  claude_code_calls_this_window: number;
  window_started_at: string;
  window_duration_minutes: number;
  max_calls_per_window: number;
}

export interface RecoveryHints {
  can_resume: boolean;
  resume_action: string;
  blocked_reason: string | null;
  escalation_needed: boolean;
}

export interface Checkpoint {
  version: number;
  session_id: string;
  phase: ProjectStatus;
  started_at: string;
  last_heartbeat: string;
  cursor: Cursor;
  llm_context: LLMContextSummary;
  rate_limit: RateLimitState;
  recovery: RecoveryHints;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  repo_path: string;
  stack: string[];
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
  current_task_id: string | null;
  coding_backend: string | null;
}

export interface Alert {
  project_id: string;
  severity: AlertSeverity;
  type: string;
  task_id: string | null;
  message: string;
  created_at: string;
  acknowledged: boolean;
}

export interface AlertList {
  alerts: Alert[];
}

export interface GlobalStats {
  daily_claude_code_calls: number;
  daily_local_llm_calls: number;
  date: string;
  cost_estimate_usd: number;
  projects_touched_today: string[];
  tasks_completed_today: number;
  approval_first_try_rate: number;
}
