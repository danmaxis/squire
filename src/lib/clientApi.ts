'use client';

export const WRITE_TOKEN_KEY = 'squire_write_token';

export function getWriteToken(): string {
  try {
    return localStorage.getItem(WRITE_TOKEN_KEY) ?? '';
  } catch {
    return '';
  }
}

export function setWriteToken(token: string) {
  try {
    localStorage.setItem(WRITE_TOKEN_KEY, token);
  } catch {
    // localStorage indisponível
  }
}

/**
 * fetch com Authorization: Bearer do token salvo no login.
 * Em 401, redireciona para /login preservando a rota atual.
 */
export async function authedFetch(
  url: string,
  init: RequestInit = {}
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getWriteToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(url, { ...init, headers });

  if (res.status === 401 && typeof window !== 'undefined') {
    const from = encodeURIComponent(
      window.location.pathname + window.location.search
    );
    window.location.assign(`/login?from=${from}`);
  }
  return res;
}
