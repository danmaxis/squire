import { Page } from '@playwright/test';
import { E2E_TOKEN } from '../playwright.config';

/** Injeta o token de escrita no localStorage (equivalente a logar em /login). */
export async function loginByToken(page: Page) {
  await page.addInitScript((token) => {
    window.localStorage.setItem('squire_write_token', token);
  }, E2E_TOKEN);
}
