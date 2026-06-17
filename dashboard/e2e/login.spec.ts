import { test, expect } from '@playwright/test';
import { E2E_TOKEN } from '../playwright.config';

test.describe('login', () => {
  test('token errado mostra erro', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('Token').fill('token-errado');
    await page.getByRole('button', { name: 'Entrar' }).click();
    await expect(page.getByText('Token inválido.')).toBeVisible();
  });

  test('token certo redireciona e persiste', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('Token').fill(E2E_TOKEN);
    await page.getByRole('button', { name: 'Entrar' }).click();
    await page.waitForURL('/');
    const stored = await page.evaluate(() =>
      window.localStorage.getItem('squire_write_token')
    );
    expect(stored).toBe(E2E_TOKEN);
  });
});
