import { describe, it, expect } from 'vitest';
import { sessionStatus } from './HealthStrip';

describe('sessionStatus', () => {
  it('sem lock: "Squire ocioso / nenhuma sessão ativa" (não "Sem sessão sem lock")', () => {
    const s = sessionStatus({
      held: false,
      holder: null,
      projectId: null,
      acquiredAt: null,
    });
    expect(s.label).toBe('Squire ocioso');
    expect(s.detail).toBe('nenhuma sessão ativa');
    expect(`${s.label} ${s.detail}`).not.toContain('Sem sessão sem lock');
  });

  it('lock expirado: ocioso com detalhe explícito', () => {
    const s = sessionStatus({
      held: false,
      holder: 'sess-x',
      projectId: 'proj',
      acquiredAt: '2026-06-11T00:00:00Z',
    });
    expect(s.label).toBe('Squire ocioso');
    expect(s.detail).toBe('lock expirado');
  });

  it('ativo: mostra o projeto rodando (não o sess-id)', () => {
    const s = sessionStatus({
      held: true,
      holder: 'sess-20260612-abc',
      projectId: 'meu-app',
      acquiredAt: '2026-06-12T00:00:00Z',
    });
    expect(s.label).toBe('Squire ativo');
    expect(s.detail).toBe('meu-app');
  });

  it('ativo sem project_id (lock antigo): cai para o holder', () => {
    const s = sessionStatus({
      held: true,
      holder: 'sess-20260612-abc',
      projectId: null,
      acquiredAt: '2026-06-12T00:00:00Z',
    });
    expect(s.detail).toBe('sess-20260612-abc');
  });
});
