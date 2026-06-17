import { test, expect } from '@playwright/test';
import { unlinkSync, writeFileSync } from 'fs';
import { join } from 'path';
import { E2E_STATE_DIR } from '../playwright.config';

/**
 * Regressão da classe "chrome congelado": Sidebar e HealthStrip leem o
 * estado a cada request em TODAS as rotas — inclusive as que eram
 * estaticamente prerenderizadas (/login, /projects/new), onde a sidebar
 * aparecia vazia e a sessão era mentirosa. Se alguém reintroduzir
 * prerender no layout, estes specs quebram.
 */

const LOCK_PATH = join(E2E_STATE_DIR, 'session.lock');
const CHROME_ROUTES = ['/projects/new', '/login'];

test.describe('chrome do layout é sempre fresco', () => {
  for (const route of CHROME_ROUTES) {
    test(`sidebar lista projetos em ${route}`, async ({ page }) => {
      await page.goto(route);
      await expect(
        page.getByRole('link', { name: /Projeto Bloqueado/ })
      ).toBeVisible();
      await expect(
        page.getByRole('link', { name: /Projeto Ativo/ })
      ).toBeVisible();
    });
  }

  test('HealthStrip ocioso: copy correta (sem "Sem sessão sem lock")', async ({ page }) => {
    await page.goto('/projects/new');
    await expect(page.getByText('Squire ocioso')).toBeVisible();
    await expect(page.getByText('nenhuma sessão ativa')).toBeVisible();
    await expect(page.getByText('Sem sessão')).not.toBeVisible();
  });

  test('HealthStrip reflete lock ativo mesmo em rota antes-estática', async ({ page }) => {
    writeFileSync(
      LOCK_PATH,
      JSON.stringify({
        holder: 'sess-e2e-chrome',
        project_id: 'proj-active',
        acquired_at: new Date().toISOString(),
        ttl_minutes: 60,
        pid: process.pid,
      })
    );
    try {
      await page.goto('/login');
      await expect(page.getByText('Squire ativo')).toBeVisible();
      await expect(page.getByText('proj-active', { exact: true })).toBeVisible();
    } finally {
      unlinkSync(LOCK_PATH);
    }
  });
});
