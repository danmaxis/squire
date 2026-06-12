import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { NextRequest } from 'next/server';

const TOKEN = 'test-token';
const PROJECT = 'proj-a';

function post(body: unknown, token: string | null = TOKEN): NextRequest {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return new NextRequest(`http://localhost/api/projects/${PROJECT}/tasks`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
}

describe('POST /api/projects/[id]/tasks', () => {
  let dataDir: string;
  let route: typeof import('./route');

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), 'squire-dash-test-'));
    mkdirSync(join(dataDir, 'projects', PROJECT), { recursive: true });
    writeFileSync(
      join(dataDir, 'projects', PROJECT, 'tasks.json'),
      JSON.stringify({ tasks: [] })
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

  it('401 sem token', async () => {
    const res = await route.POST(post({ title: 'X' }, null), params);
    expect(res.status).toBe(401);
  });

  it('cria task com defaults do modelo Python', async () => {
    const res = await route.POST(post({ title: 'Nova' }), params);
    expect(res.status).toBe(201);
    const saved = JSON.parse(
      readFileSync(join(dataDir, 'projects', PROJECT, 'tasks.json'), 'utf8')
    );
    expect(saved.tasks).toHaveLength(1);
    const t = saved.tasks[0];
    expect(t.id).toBe('task-001');
    expect(t.status).toBe('pending');
    expect(t.max_attempts).toBe(10);
    expect(t.tdd).toBe(true);
    expect(t.effort).toBe('medium');
  });

  it('409 em id duplicado', async () => {
    await route.POST(post({ title: 'A', id: 'task-001' }), params);
    const res = await route.POST(post({ title: 'B', id: 'task-001' }), params);
    expect(res.status).toBe(409);
  });

  it('400 sem título', async () => {
    const res = await route.POST(post({ description: 'sem título' }), params);
    expect(res.status).toBe(400);
  });

  it('400 com effort inválido', async () => {
    const res = await route.POST(post({ title: 'X', effort: 'épico' }), params);
    expect(res.status).toBe(400);
  });

  it('404 para projeto inexistente', async () => {
    const res = await route.POST(post({ title: 'X' }), {
      params: { id: 'nao-existe' },
    });
    expect(res.status).toBe(404);
  });

  it('409 quando squire roda o projeto (session lock)', async () => {
    writeFileSync(
      join(dataDir, 'session.lock'),
      JSON.stringify({
        holder: `sess-x-${PROJECT}`,
        project_id: PROJECT,
        acquired_at: new Date().toISOString(),
        ttl_minutes: 60,
        pid: process.pid,
      })
    );
    const res = await route.POST(post({ title: 'X' }), params);
    expect(res.status).toBe(409);
  });
});
