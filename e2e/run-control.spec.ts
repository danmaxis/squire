import { test, expect } from '@playwright/test';
import { unlinkSync, writeFileSync } from 'fs';
import { join } from 'path';
import { loginByToken } from './helpers';
import { E2E_STATE_DIR, E2E_TOKEN } from '../playwright.config';

const LOCK_PATH = join(E2E_STATE_DIR, 'session.lock');

test.describe('run control com sessão ativa', () => {
  test.beforeEach(async ({ page }) => {
    await loginByToken(page);
    writeFileSync(
      LOCK_PATH,
      JSON.stringify({
        holder: 'sess-e2e',
        project_id: 'proj-active',
        acquired_at: new Date().toISOString(),
        ttl_minutes: 60,
        pid: process.pid,
      })
    );
  });

  test.afterEach(() => {
    try {
      unlinkSync(LOCK_PATH);
    } catch {
      // já removido
    }
  });

  test('Run/Resume desabilitados; Kill habilitado no projeto do lock', async ({ page }) => {
    await page.goto('/projects/proj-active');
    await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Resume', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Kill', exact: true })).toBeEnabled();
  });

  test('POST run devolve 409 com lock ativo', async ({ request }) => {
    const res = await request.post('/api/commands', {
      headers: { Authorization: `Bearer ${E2E_TOKEN}` },
      data: { type: 'run', project_id: 'proj-active' },
    });
    expect(res.status()).toBe(409);
  });
});
