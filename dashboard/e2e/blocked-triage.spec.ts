import { test, expect } from '@playwright/test';
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';
import { loginByToken } from './helpers';
import { E2E_STATE_DIR } from '../playwright.config';

test.describe('triagem de task bloqueada', () => {
  test.beforeEach(async ({ page }) => {
    await loginByToken(page);
  });

  test('painel mostra o veredito completo do log', async ({ page }) => {
    await page.goto('/projects/proj-blocked');
    await page.getByText('Camada de persistência').click(); // expande a task

    const panel = page.getByTestId('blocked-task-panel');
    await expect(panel).toBeVisible();
    await expect(panel.getByText('Rodada 5')).toBeVisible();
    await expect(
      panel.getByText('save() retorna Week mas a rota espera tupla')
    ).toBeVisible();

    // Expande o veredito → fix_suggestion + feedback completos
    await panel.getByText('save() retorna Week mas a rota espera tupla').click();
    await expect(panel.getByText('Retorne (week, week_id) em save().')).toBeVisible();
    await expect(
      panel.getByText('Incompatibilidade crítica entre repository.save()')
    ).toBeVisible();
  });

  test('Corrigir com Claude enfileira fix_task em commands/pending', async ({ page }) => {
    await page.goto('/projects/proj-blocked');
    await page.getByText('Camada de persistência').click();

    page.once('dialog', (d) => d.accept());
    await page
      .getByTestId('blocked-task-panel')
      .getByRole('button', { name: /corrigir com claude/i })
      .click();
    await expect(page.getByText('Aguardando o agente…')).toBeVisible();

    // O agente não roda no E2E — o comando precisa estar na fila
    const pendingDir = join(E2E_STATE_DIR, 'commands', 'pending');
    await expect
      .poll(() => readdirSync(pendingDir).length, { timeout: 5000 })
      .toBeGreaterThan(0);
    const file = readdirSync(pendingDir)[0];
    const cmd = JSON.parse(readFileSync(join(pendingDir, file), 'utf8'));
    expect(cmd).toMatchObject({
      type: 'fix_task',
      project_id: 'proj-blocked',
      args: { task_id: 'task-009' },
      requested_by: 'dashboard',
    });
  });
});
