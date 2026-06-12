import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import { newTask, nextTaskId } from './taskDefaults';
import type { TaskList } from './types';

describe('newTask', () => {
  it('defaults idênticos ao modelo Python (fixture serializada por models.Task)', () => {
    // Regenere com:
    //   cd /home/ai-debian/squire && .venv/bin/python -c \
    //     "from models import Task; print(Task(id='task-001', title='Fixture').model_dump_json(indent=2))"
    const fixture = JSON.parse(
      readFileSync(
        join(__dirname, '__fixtures__', 'python-task-defaults.json'),
        'utf8'
      )
    );
    const ours = newTask({ id: 'task-001', title: 'Fixture' });
    expect(ours).toEqual(fixture);
  });

  it('aplica overrides do input', () => {
    const t = newTask({
      title: 'X',
      effort: 'high',
      tdd: false,
      skip_homologation: true,
      max_usd: 2.5,
    });
    expect(t.effort).toBe('high');
    expect(t.tdd).toBe(false);
    expect(t.skip_homologation).toBe(true);
    expect(t.max_usd).toBe(2.5);
  });
});

describe('nextTaskId', () => {
  const list = (ids: string[]): TaskList => ({
    tasks: ids.map((id) => newTask({ id, title: id })),
  });

  it('gera sequencial task-NNN', () => {
    expect(nextTaskId(list(['task-001', 'task-002']))).toBe('task-003');
  });

  it('pula colisões (mesmo comportamento do tasks_cli._next_task_id)', () => {
    // len=1 → começa em task-002, que colide → task-003
    expect(nextTaskId(list(['task-002']))).toBe('task-003');
  });
});
