import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { NextRequest } from 'next/server';

const TOKEN = 'test-token';
const PROJECT = 'proj-a';

const TASK = {
  id: 'task-001',
  title: 'Original',
  description: '',
  status: 'blocked',
  assigned_to: 'local_llm',
  attempts: 7,
  max_attempts: 10,
  homologation_result: 'rejected',
  homologation_attempt: 5,
  max_homologation_attempts: 5,
  completed_at: null,
  claude_code_assisted: false,
  subtasks: [],
  rejection_summaries: ['r1'],
  no_progress_streak: 0,
  skip_homologation: false,
  effort: 'medium',
  tdd: true,
  test_author: 'claude',
  max_usd: null,
  cost_usd: 1.2,
};

function reqFor(method: string, body?: unknown): NextRequest {
  return new NextRequest(
    `http://localhost/api/projects/${PROJECT}/tasks/task-001`,
    {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${TOKEN}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }
  );
}

describe('PATCH/DELETE /api/projects/[id]/tasks/[taskId]', () => {
  let dataDir: string;
  let route: typeof import('./route');

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), 'squire-dash-test-'));
    mkdirSync(join(dataDir, 'projects', PROJECT), { recursive: true });
    writeFileSync(
      join(dataDir, 'projects', PROJECT, 'tasks.json'),
      JSON.stringify({ tasks: [TASK] })
    );
    vi.stubEnv('SQUIRE_DATA_PATH', dataDir);
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', TOKEN);
    vi.resetModules();
    route = await import('./route');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    rmSync(dataDir, { recursive: true, force: true });
  });

  const params = { params: { id: PROJECT, taskId: 'task-001' } };

  const savedTasks = () =>
    JSON.parse(
      readFileSync(join(dataDir, 'projects', PROJECT, 'tasks.json'), 'utf8')
    ).tasks;

  it('PATCH aplica apenas campos da whitelist', async () => {
    const res = await route.PATCH(
      reqFor('PATCH', {
        title: 'Editado',
        effort: 'high',
        status: 'completed', // fora da whitelist — ignorado
        attempts: 0, // fora da whitelist — ignorado
      }),
      params
    );
    expect(res.status).toBe(200);
    const t = savedTasks()[0];
    expect(t.title).toBe('Editado');
    expect(t.effort).toBe('high');
    expect(t.status).toBe('blocked'); // intocado
    expect(t.attempts).toBe(7); // intocado
  });

  it('PATCH sem campos válidos retorna 400', async () => {
    const res = await route.PATCH(reqFor('PATCH', { attempts: 0 }), params);
    expect(res.status).toBe(400);
  });

  it('PATCH em task inexistente retorna 404', async () => {
    const res = await route.PATCH(reqFor('PATCH', { title: 'X' }), {
      params: { id: PROJECT, taskId: 'task-999' },
    });
    expect(res.status).toBe(404);
  });

  it('DELETE remove a task', async () => {
    const res = await route.DELETE(reqFor('DELETE'), params);
    expect(res.status).toBe(200);
    expect(savedTasks()).toHaveLength(0);
  });

  it('DELETE de task inexistente retorna 404', async () => {
    const res = await route.DELETE(reqFor('DELETE'), {
      params: { id: PROJECT, taskId: 'task-999' },
    });
    expect(res.status).toBe(404);
  });
});
