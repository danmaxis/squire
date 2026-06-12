import { test, expect } from '@playwright/test';
import { execFileSync } from 'child_process';
import { existsSync, mkdirSync, readdirSync, rmSync } from 'fs';
import { join } from 'path';
import { loginByToken } from './helpers';
import { E2E_STATE_DIR } from '../playwright.config';

/**
 * Roundtrip completo com o agente real (local-only): enfileira new_project
 * pela UI, roda `squire agent --once` contra o estado E2E e confere o
 * projeto aparecendo. Pulado quando o repo do squire não está na máquina.
 */

const SQUIRE_DIR = '/home/ai-debian/squire';
const REPO_ROOT = join(E2E_STATE_DIR, 'repos');

test.describe('roundtrip com o agente host', () => {
  test.skip(!existsSync(join(SQUIRE_DIR, 'agent_cli.py')), 'repo do squire ausente');

  test('new_project pela UI → agent --once → projeto criado', async ({ page }) => {
    await loginByToken(page);
    mkdirSync(REPO_ROOT, { recursive: true });

    await page.goto('/projects/new');
    await page.getByLabel('ID do projeto *').fill('e2e-roundtrip');
    await page
      .getByRole('textbox', { name: 'Repositório' })
      .fill(join(REPO_ROOT, 'e2e-roundtrip'));
    await page.getByRole('button', { name: 'Criar projeto' }).click();
    await expect(page.getByText(/Aguardando o agente|Criando projeto/)).toBeVisible();

    // Espera o comando chegar na fila, então roda o agente uma vez
    const pendingDir = join(E2E_STATE_DIR, 'commands', 'pending');
    await expect
      .poll(() => readdirSync(pendingDir).length, { timeout: 5000 })
      .toBeGreaterThan(0);

    execFileSync(join(SQUIRE_DIR, 'squire'), ['agent', '--once'], {
      env: {
        ...process.env,
        SQUIRE_STATE_ROOT: E2E_STATE_DIR,
        SQUIRE_AGENT_REPO_ROOT: REPO_ROOT,
      },
      timeout: 60_000,
    });

    // O poll do form detecta done e navega para a página do projeto
    await page.waitForURL('/projects/e2e-roundtrip', { timeout: 15_000 });
    expect(
      existsSync(join(E2E_STATE_DIR, 'projects', 'e2e-roundtrip', 'tasks.json'))
    ).toBe(true);

    rmSync(join(E2E_STATE_DIR, 'projects', 'e2e-roundtrip'), {
      recursive: true,
      force: true,
    });
  });
});
