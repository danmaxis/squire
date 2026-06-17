import { mkdirSync, rmSync, writeFileSync } from 'fs';
import { join } from 'path';
import { E2E_STATE_DIR } from '../playwright.config';

/**
 * Seed do estado para os testes E2E:
 * - proj-blocked: 1 task bloqueada com homologation_log completo
 * - proj-active: implementing, 2 tasks (1 done, 1 pending)
 * - 1 alerta crítico, global-stats, fila commands/ vazia
 */

const NOW = '2026-06-11T12:00:00+00:00';

function task(over: Record<string, unknown>) {
  return {
    id: 'task-001',
    title: 'Task',
    description: '',
    status: 'pending',
    assigned_to: 'local_llm',
    attempts: 0,
    max_attempts: 10,
    homologation_result: null,
    homologation_attempt: 0,
    max_homologation_attempts: 5,
    completed_at: null,
    claude_code_assisted: false,
    subtasks: [],
    rejection_summaries: [],
    no_progress_streak: 0,
    skip_homologation: false,
    effort: 'medium',
    tdd: true,
    test_author: 'claude',
    max_usd: null,
    cost_usd: 0,
    ...over,
  };
}

function project(id: string, over: Record<string, unknown>) {
  return {
    id,
    name: id,
    description: '',
    repo_path: `/tmp/e2e-repos/${id}`,
    stack: ['python'],
    status: 'implementing',
    created_at: NOW,
    updated_at: NOW,
    current_task_id: null,
    coding_backend: 'opencode',
    ...over,
  };
}

function write(path: string, data: unknown) {
  writeFileSync(path, JSON.stringify(data, null, 2));
}

export default function globalSetup() {
  rmSync(E2E_STATE_DIR, { recursive: true, force: true });
  for (const dir of [
    'projects/proj-blocked',
    'projects/proj-active',
    'commands/pending',
    'commands/running',
    'commands/done',
  ]) {
    mkdirSync(join(E2E_STATE_DIR, dir), { recursive: true });
  }

  // proj-blocked: task bloqueada com vereditos completos
  write(
    join(E2E_STATE_DIR, 'projects/proj-blocked/project.json'),
    project('proj-blocked', { name: 'Projeto Bloqueado', status: 'blocked' })
  );
  write(join(E2E_STATE_DIR, 'projects/proj-blocked/tasks.json'), {
    tasks: [
      task({
        id: 'task-009',
        title: 'Camada de persistência',
        status: 'blocked',
        homologation_attempt: 5,
        homologation_result: 'rejected',
        rejection_summaries: ['resumo antigo sem log'],
      }),
    ],
  });
  write(join(E2E_STATE_DIR, 'projects/proj-blocked/homologation_log.json'), {
    entries: [
      {
        timestamp: NOW,
        task_id: 'task-009',
        attempt: 5,
        approved: false,
        summary: 'save() retorna Week mas a rota espera tupla',
        feedback: 'Incompatibilidade crítica entre repository.save() e routes.py.',
        fix_suggestion: 'Retorne (week, week_id) em save().',
        suggestions: [],
        source: 'session',
        cost_usd: 0.04,
        model: 'claude-x',
      },
    ],
  });
  write(join(E2E_STATE_DIR, 'projects/proj-blocked/history.json'), {
    events: [
      {
        timestamp: NOW,
        type: 'homologation_failed',
        task_id: 'task-009',
        attempt: 5,
        summary: 'save() retorna Week mas a rota espera tupla',
        actor: 'claude_code',
      },
    ],
  });

  // proj-active: implementing
  write(
    join(E2E_STATE_DIR, 'projects/proj-active/project.json'),
    project('proj-active', { name: 'Projeto Ativo' })
  );
  write(join(E2E_STATE_DIR, 'projects/proj-active/tasks.json'), {
    tasks: [
      task({ id: 'task-001', title: 'Setup', status: 'completed' }),
      task({ id: 'task-002', title: 'Feature pendente' }),
    ],
  });
  write(join(E2E_STATE_DIR, 'projects/proj-active/history.json'), { events: [] });

  // globais
  write(join(E2E_STATE_DIR, 'alerts.json'), {
    alerts: [
      {
        project_id: 'proj-blocked',
        severity: 'critical',
        type: 'max_homologations_reached',
        task_id: 'task-009',
        message: 'Task travou após 5 homologações',
        created_at: NOW,
        acknowledged: false,
      },
    ],
  });
  write(join(E2E_STATE_DIR, 'global-stats.json'), {
    daily_claude_code_calls: 3,
    daily_local_llm_calls: 12,
    date: '2026-06-11',
    cost_estimate_usd: 1.5,
    daily_tokens: 1000,
    cost_by_model: {},
    daily_calls_unknown_cost: 0,
    projects_touched_today: ['proj-active'],
    tasks_completed_today: 1,
    tasks_homologated_today: 1,
    tasks_approved_first_try_today: 1,
    approval_first_try_rate: 100,
  });
}
