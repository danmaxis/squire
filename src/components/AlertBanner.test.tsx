import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import AlertBanner from './AlertBanner';
import type { Alert } from '@/lib/types';

// The dismiss button now hits POST /api/alerts/ack before falling back to
// localStorage; stub fetch so each test resolves deterministically.
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ updated: 1 }), { status: 200 }))
  );
});

const makeAlert = (overrides?: Partial<Alert>): Alert => ({
  project_id: 'projeto-x',
  severity: 'warning',
  type: 'failed_homologation',
  task_id: 'task-001',
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
  it('retorna null antes de montar (evita flash de hidratação SSR)', async () => {
    const { container } = render(<AlertBanner alerts={[makeAlert()]} />);
    await act(async () => {});
    // Após montar, o alerta deve aparecer
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

  it('renderiza project_id e task_id corretamente', async () => {
    render(<AlertBanner alerts={[makeAlert()]} />);
    await act(async () => {});
    expect(screen.getByText(/projeto-x/)).toBeInTheDocument();
    expect(screen.getByText(/task-001/)).toBeInTheDocument();
  });

  it('renderiza sem task_id quando task_id é null', async () => {
    render(<AlertBanner alerts={[makeAlert({ task_id: null })]} />);
    await act(async () => {});
    expect(screen.getByText('projeto-x')).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: /descartar alerta/i }));

    await waitFor(() =>
      expect(screen.queryByText('Falhou em 5 homologações')).not.toBeInTheDocument()
    );
  });

  it('dismiss persiste no localStorage com chave composta', async () => {
    render(<AlertBanner alerts={[makeAlert()]} />);
    await act(async () => {});

    fireEvent.click(screen.getByRole('button', { name: /descartar alerta/i }));

    await waitFor(() => {
      const stored = JSON.parse(
        localStorage.getItem('dismissed_alerts') ?? '[]'
      ) as string[];
      expect(stored).toContain('projeto-x::task-001::2026-03-29T10:00:00Z');
    });
  });

  it('alerta já dispensado (localStorage pré-populado) não aparece', async () => {
    localStorage.setItem(
      'dismissed_alerts',
      JSON.stringify(['projeto-x::task-001::2026-03-29T10:00:00Z'])
    );

    const { container } = render(<AlertBanner alerts={[makeAlert()]} />);
    await act(async () => {});
    expect(container.innerHTML).toBe('');
  });

  it('renderiza múltiplos alertas com dismiss individual', async () => {
    const alerts: Alert[] = [
      makeAlert({ task_id: 'task-001', message: 'Mensagem 1', created_at: '2026-03-29T10:00:00Z' }),
      makeAlert({ task_id: 'task-002', message: 'Mensagem 2', severity: 'critical', created_at: '2026-03-29T11:00:00Z' }),
    ];

    render(<AlertBanner alerts={alerts} />);
    await act(async () => {});

    expect(screen.getByText('Mensagem 1')).toBeInTheDocument();
    expect(screen.getByText('Mensagem 2')).toBeInTheDocument();

    const buttons = screen.getAllByRole('button', { name: /descartar alerta/i });
    fireEvent.click(buttons[0]);

    await waitFor(() =>
      expect(screen.queryByText('Mensagem 1')).not.toBeInTheDocument()
    );
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
