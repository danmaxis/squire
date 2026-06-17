import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { NextRequest } from 'next/server';

const TOKEN = 'test-token';
const PROJECT = 'proj-a';

const PROJECT_JSON = {
  id: PROJECT,
  name: 'Proj A',
  description: '',
  repo_path: '/tmp/proj-a',
  stack: ['python'],
  status: 'planning',
  created_at: '2026-06-01T00:00:00Z',
  updated_at: '2026-06-01T00:00:00Z',
  current_task_id: null,
  coding_backend: 'opencode',
};

function patch(body: unknown): NextRequest {
  return new NextRequest(`http://localhost/api/projects/${PROJECT}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TOKEN}`,
    },
    body: JSON.stringify(body),
  });
}

describe('PATCH /api/projects/[id]', () => {
  let dataDir: string;
  let route: typeof import('./route');

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), 'squire-dash-test-'));
    mkdirSync(join(dataDir, 'projects', PROJECT), { recursive: true });
    writeFileSync(
      join(dataDir, 'projects', PROJECT, 'project.json'),
      JSON.stringify(PROJECT_JSON)
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

  const params = { params: { id: PROJECT } };

  const saved = () =>
    JSON.parse(
      readFileSync(join(dataDir, 'projects', PROJECT, 'project.json'), 'utf8')
    );

  it('atualiza campos da whitelist e bump em updated_at', async () => {
    const res = await route.PATCH(
      patch({
        name: 'Renomeado',
        description: 'API REST',
        stack: ['python', ' flask '],
        coding_backend: 'litellm',
        status: 'implementing',
      }),
      params
    );
    expect(res.status).toBe(200);
    const p = saved();
    expect(p.name).toBe('Renomeado');
    expect(p.stack).toEqual(['python', 'flask']);
    expect(p.coding_backend).toBe('litellm');
    expect(p.status).toBe('implementing');
    expect(p.updated_at).not.toBe(PROJECT_JSON.updated_at);
    expect(p.repo_path).toBe(PROJECT_JSON.repo_path); // intocado
  });

  it('400 em backend inválido', async () => {
    const res = await route.PATCH(patch({ coding_backend: 'aider' }), params);
    expect(res.status).toBe(400);
  });

  it('400 em status inválido', async () => {
    const res = await route.PATCH(patch({ status: 'voando' }), params);
    expect(res.status).toBe(400);
  });

  it('404 em projeto inexistente', async () => {
    const res = await route.PATCH(patch({ name: 'X' }), {
      params: { id: 'nao-existe' },
    });
    expect(res.status).toBe(404);
  });
});
