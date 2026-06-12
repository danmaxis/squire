'use client';

import { useEffect, useRef, useState } from 'react';
import { authedFetch } from '@/lib/clientApi';
import type { CommandResult, CommandStatus } from '@/lib/types';

export interface CommandPollState {
  /** idle = sem comando em andamento */
  phase: 'idle' | CommandStatus | 'timeout' | 'error';
  result: CommandResult | null;
  error: string | null;
}

const POLL_MS = 2000;
const CLIENT_TIMEOUT_MS = 10 * 60 * 1000;

/**
 * Acompanha um comando enfileirado até done/failed.
 * Dica de UX: phase 'pending' por mais de ~30s sugere agente offline.
 */
export function useCommandPoll(commandId: string | null): CommandPollState {
  const [state, setState] = useState<CommandPollState>({
    phase: 'idle',
    result: null,
    error: null,
  });
  const startedAt = useRef<number>(0);

  useEffect(() => {
    if (!commandId) {
      setState({ phase: 'idle', result: null, error: null });
      return;
    }
    let cancelled = false;
    startedAt.current = Date.now();
    setState({ phase: 'pending', result: null, error: null });

    const tick = async () => {
      if (cancelled) return;
      if (Date.now() - startedAt.current > CLIENT_TIMEOUT_MS) {
        setState((s) => ({ ...s, phase: 'timeout' }));
        return;
      }
      try {
        const res = await authedFetch(`/api/commands/${commandId}`);
        if (res.status === 404) {
          // ainda não visível ou expirado — continua tentando até o timeout
          schedule();
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const view = await res.json();
        if (cancelled) return;
        if (view.status === 'done' || view.status === 'failed') {
          setState({ phase: view.status, result: view.result, error: view.result?.error ?? null });
          return;
        }
        setState({ phase: view.status, result: null, error: null });
        schedule();
      } catch (e) {
        if (cancelled) return;
        setState({ phase: 'error', result: null, error: (e as Error).message });
      }
    };

    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(tick, POLL_MS);
    };
    tick();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [commandId]);

  return state;
}
