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
 * Em 503 (writes_disabled), reescreve o body com mensagem acionável —
 * redirecionar para o login não resolveria (o problema é no servidor).
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

  if (res.status === 503) {
    const body = await res.clone().json().catch(() => ({}));
    if (body?.error === 'writes_disabled') {
      return new Response(
        JSON.stringify({
          error: 'writes_disabled',
          message:
            'Escrita desabilitada: configure DASHBOARD_WRITE_TOKEN no servidor (compose .env) e recrie o container.',
        }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }
      );
    }
  }
  return res;
}

/**
 * Enfileira um comando no agente via POST /api/commands.
 * Retorna o id do comando para polling; lança Error com a mensagem
 * do servidor (message > error > fallback) quando a resposta não é ok.
 */
export async function enqueueCommand(
  type: string,
  projectId: string | null,
  args: Record<string, unknown> = {}
): Promise<string> {
  const res = await authedFetch('/api/commands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, project_id: projectId ?? undefined, args }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message ?? body.error ?? 'request_failed');
  }
  const { id } = await res.json();
  return id;
}
