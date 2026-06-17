import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Timeline } from './Timeline';
import type { HistoryEvent } from '@/lib/types';

const makeEvent = (overrides?: Partial<HistoryEvent>): HistoryEvent => ({
  timestamp: '2026-03-29T10:00:00Z',
  type: 'task_started',
  task_id: 'task-1',
  attempt: null,
  summary: 'Evento de teste',
  actor: 'squire',
  ...overrides,
});

/** Cria N eventos com timestamps decrescentes (mais antigo → mais recente) */
const makeEvents = (count: number): HistoryEvent[] =>
  Array.from({ length: count }, (_, i) =>
    makeEvent({
      timestamp: new Date(2026, 2, 1, i).toISOString(),
      summary: `Evento ${i + 1}`,
    })
  );

describe('Timeline', () => {
  it('renderiza estado vazio quando não há eventos', () => {
    render(<Timeline events={[]} />);
    expect(screen.getByText('Nenhum evento registrado.')).toBeInTheDocument();
  });

  it('renderiza todos os eventos quando total ≤ pageSize', () => {
    render(<Timeline events={makeEvents(5)} pageSize={20} />);
    expect(screen.getByText('Evento 1')).toBeInTheDocument();
    expect(screen.getByText('Evento 5')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /ver mais/i })).not.toBeInTheDocument();
  });

  it('renderiza apenas pageSize eventos quando total > pageSize', () => {
    render(<Timeline events={makeEvents(25)} pageSize={20} />);
    expect(screen.getByText('Evento 25')).toBeInTheDocument(); // mais recente
    expect(screen.queryByText('Evento 1')).not.toBeInTheDocument(); // mais antigo fora
  });

  it('exibe botão "Ver mais N eventos" quando há mais que pageSize', () => {
    render(<Timeline events={makeEvents(25)} pageSize={20} />);
    expect(screen.getByRole('button', { name: /ver mais 5 eventos/i })).toBeInTheDocument();
  });

  it('botão "Ver mais" expande lista em pageSize', () => {
    render(<Timeline events={makeEvents(25)} pageSize={20} />);
    expect(screen.queryByText('Evento 1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /ver mais/i }));

    expect(screen.getByText('Evento 1')).toBeInTheDocument();
  });

  it('botão desaparece quando todos os eventos estão visíveis', () => {
    render(<Timeline events={makeEvents(25)} pageSize={20} />);
    fireEvent.click(screen.getByRole('button', { name: /ver mais/i }));
    expect(screen.queryByRole('button', { name: /ver mais/i })).not.toBeInTheDocument();
  });

  it('eventos são exibidos do mais recente para o mais antigo', () => {
    const events = [
      makeEvent({ timestamp: '2026-03-01T08:00:00Z', summary: 'Antigo' }),
      makeEvent({ timestamp: '2026-03-01T12:00:00Z', summary: 'Recente' }),
    ];
    render(<Timeline events={events} pageSize={20} />);
    const summaries = screen.getAllByText(/Antigo|Recente/);
    expect(summaries[0].textContent).toBe('Recente');
    expect(summaries[1].textContent).toBe('Antigo');
  });

  it('usa pageSize=20 como default', () => {
    render(<Timeline events={makeEvents(21)} />);
    // 21 eventos, default 20 → botão "Ver mais 1 eventos"
    expect(screen.getByRole('button', { name: /ver mais 1 eventos/i })).toBeInTheDocument();
  });
});
