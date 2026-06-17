import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import BlockedTaskPanel from './BlockedTaskPanel';
import { newTask } from '@/lib/taskDefaults';
import type { HomologationLogEntry, Task } from '@/lib/types';

const blockedTask = (): Task => ({
  ...newTask({ id: 'task-009', title: 'Travada' }),
  status: 'blocked',
  rejection_summaries: ['resumo antigo A', 'resumo antigo B'],
});

const entry = (over: Partial<HomologationLogEntry> = {}): HomologationLogEntry => ({
  timestamp: '2026-06-11T12:00:00Z',
  task_id: 'task-009',
  attempt: 4,
  approved: false,
  summary: 'save() retorna tipo errado',
  feedback: 'explicação longa do problema',
  fix_suggestion: 'retorne a tupla esperada',
  suggestions: [],
  source: 'session',
  cost_usd: 0.04,
  model: 'claude-x',
  ...over,
});

describe('BlockedTaskPanel', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('mostra vereditos do log (mais recente primeiro) com fix_suggestion expansível', () => {
    render(
      <BlockedTaskPanel
        task={blockedTask()}
        projectId="proj"
        logEntries={[entry({ attempt: 3, summary: 'antigo' }), entry({ attempt: 4 })]}
      />
    );
    const rounds = screen.getAllByText(/Rodada \d/);
    expect(rounds[0]).toHaveTextContent('Rodada 4');
    expect(screen.queryByText('retorne a tupla esperada')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('save() retorna tipo errado'));
    expect(screen.getByText('retorne a tupla esperada')).toBeInTheDocument();
    expect(screen.getByText('explicação longa do problema')).toBeInTheDocument();
  });

  it('faz fallback para rejection_summaries sem log', () => {
    render(
      <BlockedTaskPanel task={blockedTask()} projectId="proj" logEntries={[]} />
    );
    expect(screen.getByText('resumo antigo A')).toBeInTheDocument();
    expect(screen.getByText(/vereditos completos indisponíveis/)).toBeInTheDocument();
  });

  it('marca vereditos vindos do fix', () => {
    render(
      <BlockedTaskPanel
        task={blockedTask()}
        projectId="proj"
        logEntries={[entry({ source: 'fix' })]}
      />
    );
    expect(screen.getByText('via fix')).toBeInTheDocument();
  });

  it('botão Corrigir enfileira fix_task', async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: true,
        status: 202,
        json: async () => ({ id: '12345678-1234-1234-1234-123456789abc' }),
      })
      // polls subsequentes
      .mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: 'pending', command: null, result: null }),
      });

    render(
      <BlockedTaskPanel task={blockedTask()} projectId="proj" logEntries={[]} />
    );
    fireEvent.click(screen.getByRole('button', { name: /corrigir com claude/i }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        '/api/commands',
        expect.objectContaining({ method: 'POST' })
      );
    });
    const body = JSON.parse(
      (fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body
    );
    expect(body).toMatchObject({
      type: 'fix_task',
      project_id: 'proj',
      args: { task_id: 'task-009' },
    });
  });

  it('cancela quando o confirm é recusado', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(
      <BlockedTaskPanel task={blockedTask()} projectId="proj" logEntries={[]} />
    );
    fireEvent.click(screen.getByRole('button', { name: /corrigir com claude/i }));
    expect(fetch).not.toHaveBeenCalled();
  });
});
