import { describe, it, expect, afterEach, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { requireWriteToken } from './auth';

function req(token?: string): NextRequest {
  const headers: Record<string, string> = {};
  if (token !== undefined) headers.Authorization = `Bearer ${token}`;
  return new NextRequest('http://localhost/api/test', { headers });
}

describe('requireWriteToken', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('retorna 503 quando DASHBOARD_WRITE_TOKEN não está configurado', () => {
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', '');
    const denied = requireWriteToken(req('qualquer'));
    expect(denied?.status).toBe(503);
  });

  it('retorna 401 sem header Authorization', () => {
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', 'segredo');
    const denied = requireWriteToken(req());
    expect(denied?.status).toBe(401);
  });

  it('retorna 401 com token errado', () => {
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', 'segredo');
    const denied = requireWriteToken(req('errado'));
    expect(denied?.status).toBe(401);
  });

  it('retorna 401 com token de comprimento diferente', () => {
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', 'segredo');
    const denied = requireWriteToken(req('segredo-mais-longo'));
    expect(denied?.status).toBe(401);
  });

  it('retorna null com token correto', () => {
    vi.stubEnv('DASHBOARD_WRITE_TOKEN', 'segredo');
    expect(requireWriteToken(req('segredo'))).toBeNull();
  });
});
