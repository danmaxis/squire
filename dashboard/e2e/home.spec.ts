import { test, expect } from '@playwright/test';

test.describe('home', () => {
  test('lista projetos seedados com status e contagem de bloqueios', async ({ page }) => {
    await page.goto('/');
    // headings dos cards (o nome também aparece na sidebar — escopo via role)
    await expect(
      page.getByRole('heading', { name: 'Projeto Bloqueado' })
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Projeto Ativo' })).toBeVisible();
    // aparece no card E na pill da sidebar (agora também em PT)
    await expect(page.getByText('Bloqueado', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('1 bloqueada')).toBeVisible();
  });

  test('mostra o alerta crítico seedado', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText('Task travou após 5 homologações')).toBeVisible();
  });
});
