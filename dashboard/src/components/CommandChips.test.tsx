import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CommandChips from './CommandChips';

const HINTS = [
  { cmd: 'squire fix proj task-009', why: 'Claude corrige a task' },
  { cmd: 'squire unblock proj task-009', why: 'volta para pending' },
];

describe('CommandChips', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('lista vazia não renderiza nada', () => {
    const { container } = render(<CommandChips hints={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renderiza comando + motivo', () => {
    render(<CommandChips hints={HINTS} />);
    expect(screen.getByText('squire fix proj task-009')).toBeInTheDocument();
    expect(screen.getByText('Claude corrige a task')).toBeInTheDocument();
  });

  it('clique copia via navigator.clipboard e mostra feedback', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(<CommandChips hints={HINTS} />);
    fireEvent.click(screen.getByText('squire fix proj task-009'));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('squire fix proj task-009')
    );
    await waitFor(() =>
      expect(screen.getByText('copiado ✓')).toBeInTheDocument()
    );
  });

  it('sem clipboard API (HTTP de LAN) usa o fallback execCommand', async () => {
    vi.stubGlobal('navigator', {}); // sem .clipboard — http não-seguro
    const exec = vi.fn().mockReturnValue(true);
    document.execCommand = exec as never;

    render(<CommandChips hints={HINTS} />);
    fireEvent.click(screen.getByText('squire unblock proj task-009'));

    await waitFor(() => expect(exec).toHaveBeenCalledWith('copy'));
    await waitFor(() =>
      expect(screen.getByText('copiado ✓')).toBeInTheDocument()
    );
  });
});
