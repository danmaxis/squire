'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Play, RotateCcw, Square } from 'lucide-react';
import { enqueueCommand } from '@/lib/clientApi';
import { useCommandPoll } from '@/hooks/useCommandPoll';
import type { LockStatus } from '@/lib/squireLock';

interface RunControlsProps {
  projectId: string;
  lock: Pick<LockStatus, 'held' | 'holder' | 'projectId'>;
}

export default function RunControls({ projectId, lock }: RunControlsProps) {
  const router = useRouter();
  const [commandId, setCommandId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const poll = useCommandPoll(commandId);

  const busy = poll.phase === 'pending' || poll.phase === 'running';
  const lockIsThisProject = lock.held && lock.projectId === projectId;

  const fire = async (type: 'run' | 'resume' | 'kill') => {
    if (type === 'kill' && !window.confirm('Encerrar a sessão ativa do squire?')) {
      return;
    }
    setError(null);
    try {
      const id = await enqueueCommand(type, type === 'kill' ? null : projectId);
      setCommandId(id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    if (poll.phase === 'done' || poll.phase === 'failed') {
      if (poll.phase === 'failed') {
        setError(poll.error ?? 'comando falhou');
      }
      // o RefreshController cuida do estado contínuo; aqui só um refresh pontual
      router.refresh();
      setCommandId(null);
    }
  }, [poll.phase, poll.error, router]);

  const btn =
    'flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium disabled:opacity-40';

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => fire('run')}
        disabled={lock.held || busy}
        title={lock.held ? `Sessão ativa: ${lock.holder}` : 'squire run'}
        className={`${btn} bg-green-600 text-white hover:bg-green-500`}
      >
        <Play className="h-3.5 w-3.5" /> Run
      </button>
      <button
        onClick={() => fire('resume')}
        disabled={lock.held || busy}
        title={lock.held ? `Sessão ativa: ${lock.holder}` : 'squire resume'}
        className={`${btn} bg-blue-600 text-white hover:bg-blue-500`}
      >
        <RotateCcw className="h-3.5 w-3.5" /> Resume
      </button>
      <button
        onClick={() => fire('kill')}
        disabled={!lockIsThisProject || busy}
        title={
          lockIsThisProject
            ? 'Encerra a sessão ativa'
            : 'Só disponível quando este projeto está rodando'
        }
        className={`${btn} bg-red-600 text-white hover:bg-red-500`}
      >
        <Square className="h-3.5 w-3.5" /> Kill
      </button>
      {busy && (
        <span className="text-xs text-blue-600 dark:text-blue-400">
          {poll.phase === 'pending' ? 'aguardando agente…' : 'executando…'}
        </span>
      )}
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </div>
  );
}
