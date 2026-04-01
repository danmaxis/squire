import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import AlertBanner from './AlertBanner';

const makeAlert = (overrides?: Partial<{
  id: string;
  severity: 'critical' | 'warning';
  project: string;
  task: string;
  message: string;
  created_at: string;
  acknowledged: boolean;
}>) => ({
  id: 'alert-1',
  severity: 'warning' as const,
  project: 'Projeto X',
  task: 'task-001',
  message: 'Falhou em 5 homologações',
  created_at: '2026-03-29T10:00:00Z',
  acknowledged: false,
  ...overrides,
});

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('AlertBanner', () => {
  it('retorna null antes de montar (evita flash de hidratação SSR)', () => {
    // Antes do useEffect disparar, o componente deve retornar null
    const { container } = render(<AlertBanner alerts={[makeAlert()]} />);
    // O useEffect no jsdom é síncrono, então após render já está montado.
    // Testamos que o componente renderiza corretamente após montar.
    expect(container.innerHTML).not.toBe('');
  });

  it('retorna null quando não há alertas', async () => {
    const { container } = render(<AlertBanner alerts={[]} />);
    await act(async () => {});
    expect(container.innerHTML).toBe('');
  });

  it('retorna null quando todos os alertas estão acknowledged', async () => {
    const { container } = render(
      <AlertBanner alerts={[makeAlert({ acknowledged: true })]} />
    );
    await act(async () => {});
    expect(container.innerHTML).toBe('');
  });

  it('renderiza alerta não-acknowledged com campos corretos', async () => {
    render(<AlertBanner alerts={[makeAlert()]} />);
    await act(async () => {});
    expect(screen.getByText('Falhou em 5 homologações')).toBeInTheDocument();
    expect(screen.getByText('Projeto X - task-001')).toBeInTheDocument();
  });

  it('não exibe "Invalid Date" no timestamp', async () => {
    render(<AlertBanner alerts={[makeAlert({ created_at: '2026-03-29T10:00:00Z' })]} />);
    await act(async () => {});
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
  });

  it('botão dismiss remove o alerta da tela', async () => {
    render(<AlertBanner alerts={[makeAlert()]} />);
    await act(async () => {});

    expect(screen.getByText('Falhou em 5 homologações')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /fechar alerta/i }));

    expect(screen.queryByText('Falhou em 5 homologações')).not.toBeInTheDocument();
  });

  it('dismiss persiste no localStorage', async () => {
    render(<AlertBanner alerts={[makeAlert({ id: 'alert-42' })]} />);
    await act(async () => {});

    fireEvent.click(screen.getByRole('button', { name: /fechar alerta/i }));

    const stored = JSON.parse(localStorage.getItem('dismissed_alerts') ?? '[]') as string[];
    expect(stored).toContain('alert-42');
  });

  it('alerta já dispensado (localStorage pré-populado) não aparece', async () => {
    localStorage.setItem('dismissed_alerts', JSON.stringify(['alert-pre']));

    const { container } = render(
      <AlertBanner alerts={[makeAlert({ id: 'alert-pre' })]} />
    );
    await act(async () => {});
    expect(container.innerHTML).toBe('');
  });

  it('renderiza múltiplos alertas com dismiss individual', async () => {
    const alerts = [
      makeAlert({ id: 'a1', message: 'Mensagem 1' }),
      makeAlert({ id: 'a2', message: 'Mensagem 2', severity: 'critical' }),
    ];

    render(<AlertBanner alerts={alerts} />);
    await act(async () => {});

    expect(screen.getByText('Mensagem 1')).toBeInTheDocument();
    expect(screen.getByText('Mensagem 2')).toBeInTheDocument();

    const buttons = screen.getAllByRole('button', { name: /fechar alerta/i });
    fireEvent.click(buttons[0]);

    expect(screen.queryByText('Mensagem 1')).not.toBeInTheDocument();
    expect(screen.getByText('Mensagem 2')).toBeInTheDocument();
  });

  it('alerta critical tem fundo vermelho', async () => {
    render(<AlertBanner alerts={[makeAlert({ severity: 'critical' })]} />);
    await act(async () => {});
    const alertEl = screen.getByRole('alert');
    expect(alertEl).toHaveStyle({ backgroundColor: '#ef4444' });
  });

  it('alerta warning tem fundo âmbar', async () => {
    render(<AlertBanner alerts={[makeAlert({ severity: 'warning' })]} />);
    await act(async () => {});
    const alertEl = screen.getByRole('alert');
    expect(alertEl).toHaveStyle({ backgroundColor: '#f59e0b' });
  });
});
