import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { NextRequest } from 'next/server';

const TOKEN = 'test-token';

function post(body: unknown, token: string | null = TOKEN): NextRequest {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return new NextRequest('http://localhost/api/commands', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
}

describe('POST /api/commands', () => {
  let dataDir: string;
  let route: typeof import('./route');

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), 'squire-dash-test-'));
    vi.stubEnv('SQUIRE_DATA_PATH', dataDir);
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', TOKEN);
    vi.resetModules();
    route = await import('./route');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it('401 sem token', async () => {
    const res = await route.POST(post({ type: 'run', project_id: 'p' }, null));
    expect(res.status).toBe(401);
  });

  it('enfileira comando válido em pending/ com shape correto', async () => {
    const res = await route.POST(
      post({
        type: 'plan_tasks',
        project_id: 'meu-app',
        args: { description: 'API', mode: 'append' },
      })
    );
    expect(res.status).toBe(202);
    const { id } = await res.json();
    const files = readdirSync(join(dataDir, 'commands', 'pending'));
    expect(files).toEqual([`${id}.json`]);
    const cmd = JSON.parse(
      readFileSync(join(dataDir, 'commands', 'pending', files[0]), 'utf8')
    );
    expect(cmd).toMatchObject({
      id,
      type: 'plan_tasks',
      project_id: 'meu-app',
      args: { description: 'API', mode: 'append' },
      requested_by: 'dashboard',
    });
    expect(cmd.created_at).toBeTruthy();
  });

  it('400 em type desconhecido', async () => {
    const res = await route.POST(post({ type: 'rm_rf', project_id: 'p' }));
    expect(res.status).toBe(400);
  });

  it('400 em project_id inválido', async () => {
    const res = await route.POST(post({ type: 'run', project_id: '../etc' }));
    expect(res.status).toBe(400);
  });

  it('400 em mode inválido para plan_tasks', async () => {
    const res = await route.POST(
      post({ type: 'plan_tasks', project_id: 'p', args: { mode: 'destroy' } })
    );
    expect(res.status).toBe(400);
  });

  it('409 para run com sessão ativa', async () => {
    writeFileSync(
      join(dataDir, 'session.lock'),
      JSON.stringify({
        holder: 'sess-x',
        acquired_at: new Date().toISOString(),
        ttl_minutes: 60,
        pid: process.pid,
      })
    );
    const res = await route.POST(post({ type: 'run', project_id: 'meu-app' }));
    expect(res.status).toBe(409);
  });

  it('kill não exige project_id', async () => {
    const res = await route.POST(post({ type: 'kill' }));
    expect(res.status).toBe(202);
  });
});
