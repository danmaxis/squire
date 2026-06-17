import { describe, it, expect } from 'vitest';
import { projectCommands, taskCommands } from './cliHints';
import { newTask } from './taskDefaults';
import type { LockStatus } from './squireLock';
import type { Checkpoint, Project, Task } from './types';

const project = (over: Partial<Project> = {}): Project => ({
  id: 'meu-app',
  name: 'Meu App',
  description: '',
  repo_path: '/tmp/meu-app',
  stack: ['python'],
  status: 'implementing',
  created_at: '2026-06-12T00:00:00Z',
  updated_at: '2026-06-12T00:00:00Z',
  current_task_id: null,
  coding_backend: 'opencode',
  ...over,
});

const freeLock: LockStatus = {
  held: false, holder: null, projectId: null, pid: null,
  acquiredAt: null, ageSeconds: null,
};

const heldLock = (projectId: string): LockStatus => ({
  held: true, holder: 'sess-x', projectId, pid: 1,
  acquiredAt: '2026-06-12T00:00:00Z', ageSeconds: 10,
});

const resumableCheckpoint = (taskId: string): Checkpoint => ({
  version: 1,
  session_id: 'sess-morta',
  phase: 'implementing',
  started_at: '2026-06-12T00:00:00Z',
  last_heartbeat: '2026-06-12T00:00:00Z',
  cursor: {
    current_task_id: taskId, current_subtask_id: null,
    step: 'homologation', attempt: 1, homologation_attempt: 2,
  },
  llm_context: {
    last_instruction: '', files_touched: [], last_error: null,
    tests_passing: 0, tests_failing: 0, test_summary: '',
  },
  rate_limit: {
    claude_code_calls_this_window: 0, window_started_at: '2026-06-12T00:00:00Z',
    window_duration_minutes: 30, max_calls_per_window: 10,
    max_daily_usd: 0, daily_cost_usd: 0, daily_cost_date: '2026-06-12',
  },
  recovery: {
    can_resume: true, resume_action: 'continue',
    blocked_reason: null, escalation_needed: false,
  },
});

const task = (over: Partial<Task>): Task => ({ ...newTask({ id: 't', title: 'T' }), ...over });

const cmds = (hints: { cmd: string }[]) => hints.map((h) => h.cmd);

describe('projectCommands', () => {
  it('rodando ESTE projeto → kill (e nada de run/resume)', () => {
    const hints = projectCommands({
      project: project(),
      tasks: [task({ status: 'pending' })],
      lock: heldLock('meu-app'),
      checkpoint: null,
    });
    expect(cmds(hints)).toEqual(['squire kill']);
  });

  it('rodando OUTRO projeto → sem comandos de execução', () => {
    const hints = projectCommands({
      project: project(),
      tasks: [task({ status: 'pending' })],
      lock: heldLock('outro'),
      checkpoint: null,
    });
    expect(cmds(hints)).toEqual([]);
  });

  it('parado + checkpoint retomável → resume (não run)', () => {
    const hints = projectCommands({
      project: project(),
      tasks: [task({ status: 'pending' })],
      lock: freeLock,
      checkpoint: resumableCheckpoint('task-004'),
    });
    expect(cmds(hints)).toEqual(['squire resume meu-app']);
    expect(hints[0].why).toContain('task-004');
  });

  it('parado + pendentes sem checkpoint → run + bg', () => {
    const hints = projectCommands({
      project: project(),
      tasks: [task({ status: 'pending' })],
      lock: freeLock,
      checkpoint: null,
    });
    expect(cmds(hints)).toEqual(['squire run meu-app', 'squire bg meu-app']);
  });

  it('com bloqueadas → unblock entra na lista', () => {
    const hints = projectCommands({
      project: project({ status: 'blocked' }),
      tasks: [task({ status: 'blocked' })],
      lock: freeLock,
      checkpoint: null,
    });
    expect(cmds(hints)).toContain('squire unblock meu-app');
  });

  it('projeto completed → nada', () => {
    const hints = projectCommands({
      project: project({ status: 'completed' }),
      tasks: [task({ status: 'completed' })],
      lock: freeLock,
      checkpoint: resumableCheckpoint('task-001'),
    });
    expect(cmds(hints)).toEqual([]);
  });
});

describe('taskCommands', () => {
  const opts = { lockHeld: false, resumableTaskId: null };

  it('blocked → fix/unblock/reset com ids corretos', () => {
    const hints = taskCommands('meu-app', task({ id: 'task-009', status: 'blocked' }), opts);
    expect(cmds(hints)).toEqual([
      'squire fix meu-app task-009',
      'squire unblock meu-app task-009',
      'squire reset meu-app task-009',
    ]);
  });

  it('homologating com sessão morta nesta task → resume', () => {
    const hints = taskCommands(
      'meu-app',
      task({ id: 'task-004', status: 'homologating' }),
      { lockHeld: false, resumableTaskId: 'task-004' }
    );
    expect(cmds(hints)).toEqual(['squire resume meu-app']);
  });

  it('homologating com lock vivo → nada (sessão está cuidando)', () => {
    const hints = taskCommands(
      'meu-app',
      task({ id: 'task-004', status: 'homologating' }),
      { lockHeld: true, resumableTaskId: 'task-004' }
    );
    expect(hints).toEqual([]);
  });

  it('pending/completed → nada', () => {
    expect(taskCommands('p', task({ status: 'pending' }), opts)).toEqual([]);
    expect(taskCommands('p', task({ status: 'completed' }), opts)).toEqual([]);
  });
});
