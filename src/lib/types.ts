/**
 * Enums espelhados dos models.py como union types de strings
 * para garantir tipagem estrita e compatibilidade com JSON do Python.
 */

export type ProjectStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type EventType = 'task_started' | 'task_completed' | 'task_failed' | 'checkpoint_created' | 'alert_generated' | 'commit_created';
export type AlertSeverity = 'info' | 'warning' | 'error' | 'critical';
export type Actor = 'system' | 'user' | 'agent' | 'external';

/**
 * Interface: Project
 * Espelha o modelo Pydantic Project
 */
export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
  owner_id: string;
  config: Record<string, unknown>;
}

/**
 * Interface: Task
 * Espelha o modelo Pydantic Task
 */
export interface Task {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status: TaskStatus;
  priority: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

/**
 * Interface: Subtask
 * Espelha o modelo Pydantic Subtask
 */
export interface Subtask {
  id: string;
  task_id: string;
  name: string;
  description: string;
  status: TaskStatus;
  order: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

/**
 * Interface: HistoryEvent
 * Espelha o modelo Pydantic HistoryEvent
 */
export interface HistoryEvent {
  id: string;
  project_id: string;
  task_id: string | null;
  subtask_id: string | null;
  event_type: EventType;
  actor: Actor;
  timestamp: string; // ISO 8601
  message: string;
  metadata: Record<string, unknown>;
}

/**
 * Interface: CommitSummary
 * Espelha o modelo Pydantic CommitSummary
 */
export interface CommitSummary {
  id: string;
  project_id: string;
  task_id: string | null;
  commit_hash: string;
  message: string;
  author: string;
  timestamp: string; // ISO 8601
  changes: Array<{
    file: string;
    action: 'added' | 'modified' | 'deleted';
  }>;
}

/**
 * Interface: Alert
 * Espelha o modelo Pydantic Alert
 */
export interface Alert {
  id: string;
  project_id: string;
  task_id: string | null;
  severity: AlertSeverity;
  title: string;
  description: string;
  timestamp: string; // ISO 8601
  resolved: boolean;
  resolved_at: string | null;
  metadata: Record<string, unknown>;
}

/**
 * Interface: GlobalStats
 * Espelha o modelo Pydantic GlobalStats
 */
export interface GlobalStats {
  total_projects: number;
  active_projects: number;
  completed_projects: number;
  total_tasks: number;
  running_tasks: number;
  failed_tasks: number;
  total_alerts: number;
  critical_alerts: number;
  last_updated: string; // ISO 8601
}

/**
 * Interface: Checkpoint
 * Espelha o modelo Pydantic Checkpoint
 */
export interface Checkpoint {
  id: string;
  project_id: string;
  task_id: string | null;
  name: string;
  description: string;
  timestamp: string; // ISO 8601
  state_snapshot: Record<string, unknown>;
  metadata: Record<string, unknown>;
}