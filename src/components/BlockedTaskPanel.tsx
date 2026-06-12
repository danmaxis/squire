'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, ChevronRight, Wrench } from 'lucide-react';
import { authedFetch } from '@/lib/clientApi';
import { useCommandPoll } from '@/hooks/useCommandPoll';
import type { HomologationLogEntry, Task } from '@/lib/types';

interface BlockedTaskPanelProps {
  task: Task;
  projectId: string;
  logEntries: HomologationLogEntry[];
}

function VerdictCard({ entry }: { entry: HomologationLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded border border-red-200 bg-red-50/50 p-3 text-sm">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-2 text-left"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
        )}
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-red-800">
              Rodada {entry.attempt}
            </span>
            {entry.source === 'fix' && (
              <span className="rounded bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-700">
                via fix
              </span>
            )}
            <span className="text-xs text-gray-500">
              {new Date(entry.timestamp).toLocaleString('pt-BR')}
            </span>
            {entry.cost_usd > 0 && (
              <span className="font-mono text-xs text-gray-500">
                ${entry.cost_usd.toFixed(3)}
              </span>
            )}
          </div>
          <p className="mt-1 text-gray-800">{entry.summary}</p>
        </div>
      </button>

      {expanded && (
        <div className="ml-6 mt-2 space-y-2">
          {entry.fix_suggestion && (
            <div className="rounded bg-amber-50 p-2">
              <p className="text-xs font-semibold uppercase text-amber-700">
                Como corrigir
              </p>
              <p className="whitespace-pre-wrap text-gray-800">
                {entry.fix_suggestion}
              </p>
            </div>
          )}
          {entry.feedback && (
            <div>
              <p className="text-xs font-semibold uppercase text-gray-500">
                Feedback completo
              </p>
              <p className="whitespace-pre-wrap text-gray-700">{entry.feedback}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BlockedTaskPanel({
  task,
  projectId,
  logEntries,
}: BlockedTaskPanelProps) {
  const router = useRouter();
  const [commandId, setCommandId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const poll = useCommandPoll(commandId);
  const busy = poll.phase === 'pending' || poll.phase === 'running';

  const taskVerdicts = logEntries
    .filter((e) => e.task_id === task.id && !e.approved)
    .reverse(); // mais recente primeiro

  useEffect(() => {
    if (poll.phase === 'done') {
      setCommandId(null);
      router.refresh(); // task agora completed
    }
    if (poll.phase === 'failed') {
      // exit 6 = rodou mas foi rejeitada — refresh mostra o novo veredito
      setError(
        poll.result?.stderr_tail ||
          poll.result?.stdout_tail?.split('\n').slice(-3).join('\n') ||
          poll.error ||
          'fix falhou'
      );
      setCommandId(null);
      router.refresh();
    }
    if (poll.phase === 'timeout') {
      setError(
        'Sem resposta dentro do tempo — o fix pode ainda estar rodando no host (squire agent).'
      );
      setCommandId(null);
    }
  }, [poll.phase, poll.error, poll.result, router]);

  const startFix = async () => {
    if (
      !window.confirm(
        'Claude vai implementar a correção diretamente, rodar os testes e fazer 1 rodada de homologação (~5–8 min, ~$0.10–0.30). Continuar?'
      )
    ) {
      return;
    }
    setError(null);
    try {
      const res = await authedFetch('/api/commands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'fix_task',
          project_id: projectId,
          args: { task_id: task.id },
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.error ?? 'request_failed');
      }
      const { id } = await res.json();
      setCommandId(id);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="mt-3 space-y-2" data-testid="blocked-task-panel">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-red-700">
          Task bloqueada — histórico de rejeições
        </span>
        <button
          onClick={startFix}
          disabled={busy}
          className="flex items-center gap-1.5 rounded bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-50"
        >
          <Wrench className="h-3.5 w-3.5" />
          {busy ? 'Corrigindo…' : 'Corrigir com Claude'}
        </button>
      </div>

      {busy && (
        <p className="text-sm text-purple-600">
          {poll.phase === 'pending'
            ? 'Aguardando o agente…'
            : 'Claude corrigindo — implementação + testes + homologação (~5–8 min).'}
        </p>
      )}
      {error && (
        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-red-50 p-2 text-xs text-red-700">
          {error}
        </pre>
      )}

      {taskVerdicts.length > 0 ? (
        <div className="space-y-2">
          {taskVerdicts.map((entry, i) => (
            <VerdictCard key={`${entry.attempt}-${i}`} entry={entry} />
          ))}
        </div>
      ) : task.rejection_summaries.length > 0 ? (
        <div className="space-y-1">
          <p className="text-xs text-gray-500">
            (vereditos completos indisponíveis para rodadas antigas — resumos:)
          </p>
          {[...task.rejection_summaries].reverse().map((summary, i) => (
            <div
              key={i}
              className="rounded border border-red-200 bg-red-50/50 p-2 text-sm text-gray-800"
            >
              {summary}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500">Sem histórico de rejeições registrado.</p>
      )}
    </div>
  );
}
