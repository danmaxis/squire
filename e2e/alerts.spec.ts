import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { loginByToken } from './helpers';
import { E2E_STATE_DIR } from '../playwright.config';

const ALERTS_PATH = join(E2E_STATE_DIR, 'alerts.json');

test.describe('alertas', () => {
  let original: string;

  test.beforeEach(() => {
    original = readFileSync(ALERTS_PATH, 'utf8');
  });

  test.afterEach(() => {
    // Restaura o estado — outros specs dependem do alerta não-reconhecido
    writeFileSync(ALERTS_PATH, original);
  });

  test('ack pelo banner persiste acknowledged=true', async ({ page }) => {
    await loginByToken(page);
    await page.goto('/');

    const banner = page.getByText('Task travou após 5 homologações');
    await expect(banner).toBeVisible();
    await page.getByRole('button', { name: 'Reconhecer alerta' }).first().click();

    await expect
      .poll(() => {
        const alerts = JSON.parse(
          readFileSync(join(E2E_STATE_DIR, 'alerts.json'), 'utf8')
        ).alerts;
        return alerts[0]?.acknowledged;
      }, { timeout: 5000 })
      .toBe(true);
  });
});
