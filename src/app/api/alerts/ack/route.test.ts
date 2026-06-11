/**
 * Padrão de teste de route handlers:
 * squireStatePath.ts lê SQUIRE_DATA_PATH em module-load, então o env precisa
 * ser stubado ANTES do import — por isso vi.resetModules() + import dinâmico.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { NextRequest } from 'next/server';

const TOKEN = 'test-token';

function post(body: unknown, token: string | null = TOKEN): NextRequest {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return new NextRequest('http://localhost/api/alerts/ack', {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
}

const ALERT = {
  project_id: 'proj-a',
  severity: 'critical',
  type: 'max_homologations_reached',
  task_id: 'task-001',
  message: 'falhou',
  created_at: '2026-06-11T00:00:00Z',
  acknowledged: false,
};

describe('POST /api/alerts/ack', () => {
  let dataDir: string;
  let route: typeof import('./route');

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), 'squire-dash-test-'));
    writeFileSync(join(dataDir, 'alerts.json'), JSON.stringify({ alerts: [ALERT] }));
    vi.stubEnv('SQUIRE_DATA_PATH', dataDir);
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', TOKEN);
    vi.resetModules();
    route = await import('./route');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it('exige token (401 sem Authorization)', async () => {
    const res = await route.POST(post({ ...ALERT, dismiss: false }, null));
    expect(res.status).toBe(401);
  });

  it('responde 503 quando token não configurado no servidor', async () => {
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', '');
    const res = await route.POST(post({ ...ALERT, dismiss: false }));
    expect(res.status).toBe(503);
  });

  it('ack marca acknowledged=true no arquivo', async () => {
    const res = await route.POST(
      post({
        project_id: ALERT.project_id,
        task_id: ALERT.task_id,
        created_at: ALERT.created_at,
      })
    );
    expect(res.status).toBe(200);
    const saved = JSON.parse(readFileSync(join(dataDir, 'alerts.json'), 'utf8'));
    expect(saved.alerts[0].acknowledged).toBe(true);
  });

  it('dismiss remove o alerta', async () => {
    const res = await route.POST(
      post({
        project_id: ALERT.project_id,
        task_id: ALERT.task_id,
        created_at: ALERT.created_at,
        dismiss: true,
      })
    );
    expect(res.status).toBe(200);
    const saved = JSON.parse(readFileSync(join(dataDir, 'alerts.json'), 'utf8'));
    expect(saved.alerts).toHaveLength(0);
  });

  it('alerta inexistente devolve 404', async () => {
    const res = await route.POST(
      post({ project_id: 'x', task_id: null, created_at: '2020-01-01T00:00:00Z' })
    );
    expect(res.status).toBe(404);
  });
});
