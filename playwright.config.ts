import { defineConfig } from '@playwright/test';
import { join } from 'path';

/**
 * Suite E2E: sobe `next dev` numa porta dedicada apontando para um estado
 * seedado em e2e/.state (recriado pelo global-setup a cada run). Token de
 * escrita fixo 'e2e-token'. Chromium only — ferramenta de LAN.
 */

export const E2E_PORT = 3199;
export const E2E_TOKEN = 'e2e-token';
export const E2E_STATE_DIR = join(__dirname, 'e2e', '.state');

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 30_000,
  retries: 0,
  workers: 1, // estado compartilhado no filesystem — specs não podem competir
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${E2E_PORT}`,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `npx next dev -p ${E2E_PORT}`,
    port: E2E_PORT,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      SQUIRE_DATA_PATH: E2E_STATE_DIR,
      DASHBOARD_WRITE_TOKEN: E2E_TOKEN,
    },
  },
});
