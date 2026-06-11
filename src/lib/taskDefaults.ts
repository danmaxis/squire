import type { Effort, Task, TaskList, TestAuthor } from './types';

/**
 * Espelho dos defaults do modelo Python `Task` (squire/models.py).
 * Qualquer mudança lá precisa refletir aqui — o teste taskDefaults.test.ts
 * compara contra uma fixture serializada pelo modelo real.
 */

export interface NewTaskInput {
  id?: string;
  title: string;
  description?: string;
  effort?: Effort;
  tdd?: boolean;
  test_author?: TestAuthor;
  skip_homologation?: boolean;
  max_attempts?: number;
  max_homologation_attempts?: number;
  max_usd?: number | null;
}

export function newTask(input: NewTaskInput): Task {
  return {
    id: input.id ?? '',
    title: input.title,
    description: input.description ?? '',
    status: 'pending',
    assigned_to: 'local_llm',
    attempts: 0,
    max_attempts: input.max_attempts ?? 10,
    homologation_result: null,
    homologation_attempt: 0,
    max_homologation_attempts: input.max_homologation_attempts ?? 5,
    completed_at: null,
    claude_code_assisted: false,
    subtasks: [],
    rejection_summaries: [],
    no_progress_streak: 0,
    skip_homologation: input.skip_homologation ?? false,
    effort: input.effort ?? 'medium',
    tdd: input.tdd ?? true,
    test_author: input.test_author ?? 'claude',
    max_usd: input.max_usd ?? null,
    cost_usd: 0,
  };
}

/** Campos editáveis via PATCH — status fica de fora (rota /action cuida). */
export const EDITABLE_TASK_FIELDS = [
  'title',
  'description',
  'effort',
  'tdd',
  'test_author',
  'skip_homologation',
  'max_attempts',
  'max_homologation_attempts',
  'max_usd',
] as const;

export type EditableTaskField = (typeof EDITABLE_TASK_FIELDS)[number];

/** Mesmo algoritmo de tasks_cli._next_task_id (task-NNN sequencial sem colisão). */
export function nextTaskId(taskList: TaskList): string {
  const existing = new Set(taskList.tasks.map((t) => t.id));
  let n = taskList.tasks.length + 1;
  for (;;) {
    const candidate = `task-${String(n).padStart(3, '0')}`;
    if (!existing.has(candidate)) return candidate;
    n += 1;
  }
}

export const EFFORTS: Effort[] = ['low', 'medium', 'high'];
export const TEST_AUTHORS: TestAuthor[] = ['claude', 'local'];
