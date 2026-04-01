import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import AlertBanner from './AlertBanner';

const makeAlert = (overrides?: Partial<{
  id: string;
  severity: 'critical' | 'warning';
  project: string;
  task: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
}>) => ({
  id: 'alert-1',
  severity: 'warning' as const,
  project: 'Projeto X',
  task: 'task-001',
  message: 'Falhou em 5 homologações',
  timestamp: '2026-03-29T10:00:00Z',
  acknowledged: false,
  ...overrides,
});

beforeEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('AlertBanner', () => {
  it('retorna null quando não há alertas', () => {
    const { container } = render(<AlertBanner alerts={[]} />);
    expect(container.innerHTML).toBe('');
  });

  it('retorna null quando todos os alertas estão acknowledged', () => {
    const { container } = render(
      <AlertBanner alerts={[makeAlert({ acknowledged: true })]} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renderiza alerta não-acknowledged', () => {
    render(<AlertBanner alerts={[makeAlert()]} />);
    expect(screen.getByText('Falhou em 5 homologações')).toBeInTheDocument();
    expect(screen.getByText('Projeto X - task-001')).toBeInTheDocument();
  });

  it('botão dismiss remove o alerta da tela', () => {
    render(<AlertBanner alerts={[makeAlert()]} />);
    expect(screen.getByText('Falhou em 5 homologações')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /fechar alerta/i }));

    expect(screen.queryByText('Falhou em 5 homologações')).not.toBeInTheDocument();
  });

  it('dismiss persiste no sessionStorage', () => {
    render(<AlertBanner alerts={[makeAlert({ id: 'alert-42' })]} />);
    fireEvent.click(screen.getByRole('button', { name: /fechar alerta/i }));

    const stored = JSON.parse(sessionStorage.getItem('dismissed_alerts') ?? '[]') as string[];
    expect(stored).toContain('alert-42');
  });

  it('alerta já dispensado (sessionStorage pré-populado) não aparece', () => {
    sessionStorage.setItem('dismissed_alerts', JSON.stringify(['alert-pre']));

    const { container } = render(
      <AlertBanner alerts={[makeAlert({ id: 'alert-pre' })]} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renderiza múltiplos alertas com dismiss individual', () => {
    const alerts = [
      makeAlert({ id: 'a1', message: 'Mensagem 1' }),
      makeAlert({ id: 'a2', message: 'Mensagem 2', severity: 'critical' }),
    ];

    render(<AlertBanner alerts={alerts} />);
    expect(screen.getByText('Mensagem 1')).toBeInTheDocument();
    expect(screen.getByText('Mensagem 2')).toBeInTheDocument();

    const buttons = screen.getAllByRole('button', { name: /fechar alerta/i });
    fireEvent.click(buttons[0]);

    expect(screen.queryByText('Mensagem 1')).not.toBeInTheDocument();
    expect(screen.getByText('Mensagem 2')).toBeInTheDocument();
  });

  it('alerta critical tem fundo vermelho', () => {
    render(<AlertBanner alerts={[makeAlert({ severity: 'critical' })]} />);
    const alertEl = screen.getByRole('alert');
    expect(alertEl).toHaveStyle({ backgroundColor: '#ef4444' });
  });

  it('alerta warning tem fundo âmbar', () => {
    render(<AlertBanner alerts={[makeAlert({ severity: 'warning' })]} />);
    const alertEl = screen.getByRole('alert');
    expect(alertEl).toHaveStyle({ backgroundColor: '#f59e0b' });
  });
});
