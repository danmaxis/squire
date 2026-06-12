'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import { authedFetch } from '@/lib/clientApi';
import { useCommandPoll } from '@/hooks/useCommandPoll';

interface PlanTasksPanelProps {
  projectId: string;
  initialDescription: string;
}

export default function PlanTasksPanel({
  projectId,
  initialDescription,
}: PlanTasksPanelProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState(initialDescription);
  const [mode, setMode] = useState<'append' | 'replace'>('append');
  const [commandId, setCommandId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [doneMsg, setDoneMsg] = useState<string | null>(null);

  const poll = useCommandPoll(commandId);
  const busy = poll.phase === 'pending' || poll.phase === 'running';

  useEffect(() => {
    if (poll.phase === 'done') {
      setDoneMsg('Tasks planejadas — lista atualizada.');
      setCommandId(null);
      router.refresh();
    }
    if (poll.phase === 'failed') {
      setError(poll.result?.stderr_tail || poll.error || 'falhou');
      setCommandId(null);
    }
    if (poll.phase === 'timeout') {
      setError('Sem resposta do agente — `squire agent` está rodando na VM?');
      setCommandId(null);
    }
  }, [poll.phase, poll.error, poll.result, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setDoneMsg(null);
    try {
      const res = await authedFetch('/api/commands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'plan_tasks',
          project_id: projectId,
          args: { description, mode },
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.error ?? 'request_failed');
      }
      const { id } = await res.json();
      setCommandId(id);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
        aria-expanded={open}
      >
        <Sparkles className="h-4 w-4 text-purple-500" />
        Planejar tasks com Claude
      </button>

      {open && (
        <form onSubmit={handleSubmit} className="space-y-3 border-t border-gray-100 p-4 dark:border-gray-700">
          <label className="block text-sm">
            <span className="text-gray-700 dark:text-gray-300">O que o projeto deve fazer?</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder="Descreva funcionalidades, stack e restrições — quanto mais específico, melhor o plano."
              className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
            />
          </label>

          <div className="flex gap-6 text-sm text-gray-700 dark:text-gray-300">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={mode === 'append'}
                onChange={() => setMode('append')}
              />
              Adicionar às tasks existentes
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={mode === 'replace'}
                onChange={() => setMode('replace')}
              />
              <span>
                Substituir tudo{' '}
                <span className="text-xs text-red-500 dark:text-red-400">(descarta o backlog atual)</span>
              </span>
            </label>
          </div>

          {busy && (
            <p className="text-sm text-purple-600 dark:text-purple-300">
              {poll.phase === 'pending'
                ? 'Aguardando o agente…'
                : 'Claude planejando… pode levar ~3 min.'}
            </p>
          )}
          {doneMsg && <p className="text-sm text-green-600 dark:text-green-400">{doneMsg}</p>}
          {error && (
            <pre className="max-h-32 overflow-auto rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/50 dark:text-red-300">
              {error}
            </pre>
          )}

          <button
            type="submit"
            disabled={busy || !description.trim()}
            className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
          >
            {busy ? 'Planejando…' : 'Planejar'}
          </button>
        </form>
      )}
    </div>
  );
}
