import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RunControls from './RunControls';

describe('RunControls', () => {
  it('habilita Run/Resume e desabilita Kill quando livre', () => {
    render(
      <RunControls
        projectId="meu-app"
        lock={{ held: false, holder: null, projectId: null }}
      />
    );
    expect(screen.getByRole('button', { name: /run/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /resume/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /kill/i })).toBeDisabled();
  });

  it('desabilita Run/Resume quando outra sessão roda', () => {
    render(
      <RunControls
        projectId="meu-app"
        lock={{ held: true, holder: 'sess-x', projectId: 'outro-projeto' }}
      />
    );
    expect(screen.getByRole('button', { name: /run/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /resume/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /kill/i })).toBeDisabled();
  });

  it('habilita Kill quando o lock é deste projeto', () => {
    render(
      <RunControls
        projectId="meu-app"
        lock={{ held: true, holder: 'sess-x', projectId: 'meu-app' }}
      />
    );
    expect(screen.getByRole('button', { name: /kill/i })).toBeEnabled();
  });
});
