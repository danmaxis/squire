import { test, expect } from '@playwright/test';
import { unlinkSync, writeFileSync } from 'fs';
import { join } from 'path';
import { E2E_STATE_DIR } from '../playwright.config';

const LOCK_PATH = join(E2E_STATE_DIR, 'session.lock');

test.describe('comandos de desobstrução', () => {
  test('task bloqueada mostra fix/unblock/reset e copia ao clicar', async ({
    page,
    context,
  }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/projects/proj-blocked');
    await page.getByText('Camada de persistência').click();

    const panel = page.getByTestId('blocked-task-panel');
    await expect(panel.getByText('squire fix proj-blocked task-009')).toBeVisible();
    await expect(
      panel.getByText('squire unblock proj-blocked task-009')
    ).toBeVisible();
    await expect(panel.getByText('squire reset proj-blocked task-009')).toBeVisible();

    await panel.getByText('squire fix proj-blocked task-009').click();
    await expect(panel.getByText('copiado ✓')).toBeVisible();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied).toBe('squire fix proj-blocked task-009');
  });

  test('projeto parado com pendentes mostra run/bg; bloqueado mostra unblock', async ({
    page,
  }) => {
    await page.goto('/projects/proj-active');
    await expect(page.getByText('squire run proj-active')).toBeVisible();
    await expect(page.getByText('squire bg proj-active')).toBeVisible();

    await page.goto('/projects/proj-blocked');
    await expect(page.getByText('squire unblock proj-blocked', { exact: true })).toBeVisible();
  });

  test('com sessão ativa DESTE projeto mostra squire kill', async ({ page }) => {
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
    try {
      await page.goto('/projects/proj-active');
      await expect(page.getByText('squire kill')).toBeVisible();
      await expect(page.getByText('squire run proj-active')).not.toBeVisible();
    } finally {
      unlinkSync(LOCK_PATH);
    }
  });
});
