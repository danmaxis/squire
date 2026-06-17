import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { NextRequest } from 'next/server';

const TOKEN = 'test-token';
const UUID = '12345678-1234-1234-1234-123456789abc';

function get(id: string): NextRequest {
  return new NextRequest(`http://localhost/api/commands/${id}`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
}

describe('GET /api/commands/[id]', () => {
  let dataDir: string;
  let route: typeof import('./route');

  beforeEach(async () => {
    dataDir = mkdtempSync(join(tmpdir(), 'squire-dash-test-'));
    for (const d of ['pending', 'running', 'done']) {
      mkdirSync(join(dataDir, 'commands', d), { recursive: true });
    }
    vi.stubEnv('SQUIRE_DATA_PATH', dataDir);
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', TOKEN);
    vi.resetModules();
    route = await import('./route');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    rmSync(dataDir, { recursive: true, force: true });
  });

  it('400 para id fora do formato uuid (guarda de traversal)', async () => {
    const res = await route.GET(get('..%2F..%2Fetc'), {
      params: { id: '../../etc' },
    });
    expect(res.status).toBe(400);
  });

  it('404 para comando desconhecido', async () => {
    const res = await route.GET(get(UUID), { params: { id: UUID } });
    expect(res.status).toBe(404);
  });

  it('reporta pending', async () => {
    writeFileSync(
      join(dataDir, 'commands', 'pending', `${UUID}.json`),
      JSON.stringify({ id: UUID, type: 'run', project_id: 'p', args: {} })
    );
    const res = await route.GET(get(UUID), { params: { id: UUID } });
    const body = await res.json();
    expect(body.status).toBe('pending');
  });

  it('reporta done com o resultado', async () => {
    writeFileSync(
      join(dataDir, 'commands', 'done', `${UUID}.json`),
      JSON.stringify({
        id: UUID,
        type: 'run',
        project_id: 'p',
        status: 'done',
        exit_code: 0,
        stdout_tail: 'ok',
        stderr_tail: '',
        started_at: null,
        finished_at: null,
        error: null,
      })
    );
    const res = await route.GET(get(UUID), { params: { id: UUID } });
    const body = await res.json();
    expect(body.status).toBe('done');
    expect(body.result.exit_code).toBe(0);
  });
});
