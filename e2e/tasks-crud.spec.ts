import { test, expect } from '@playwright/test';
import { loginByToken } from './helpers';

test.describe('task CRUD pelo modal', () => {
  test.beforeEach(async ({ page }) => {
    await loginByToken(page);
  });

  test('cria, edita e exclui uma task', async ({ page }) => {
    await page.goto('/projects/proj-active');

    // Criar
    await page.getByRole('button', { name: '+ Nova task' }).click();
    await page.getByLabel('Título *').fill('Task criada no E2E');
    await page.getByRole('button', { name: 'Criar task' }).click();
    await expect(
      page.getByRole('heading', { name: 'Task criada no E2E' })
    ).toBeVisible();

    // Helper: linha (header) da task pelo heading — sobe ao container do header
    const rowOf = (title: string) =>
      page
        .getByRole('heading', { name: title })
        .locator('xpath=ancestor::div[contains(@class,"p-4")][1]');

    // Editar (menu ⋯ da task recém-criada)
    await rowOf('Task criada no E2E').getByTitle('Ações da task').click();
    await page.getByRole('menuitem', { name: 'Editar task' }).click();
    const titleInput = page.getByLabel('Título *');
    await titleInput.fill('Task editada no E2E');
    await page.getByRole('button', { name: 'Salvar' }).click();
    await expect(
      page.getByRole('heading', { name: 'Task editada no E2E' })
    ).toBeVisible();

    // Excluir
    page.once('dialog', (d) => d.accept());
    await rowOf('Task editada no E2E').getByTitle('Ações da task').click();
    await page.getByRole('menuitem', { name: 'Excluir task' }).click();
    await expect(
      page.getByRole('heading', { name: 'Task editada no E2E' })
    ).not.toBeVisible();
  });
});
