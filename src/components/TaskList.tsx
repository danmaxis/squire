'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { authedFetch } from '@/lib/clientApi';
import TaskForm from './TaskForm';
import { Task } from '@/lib/types';

interface TaskListProps {
  tasks: Task[];
  projectId?: string;
}

type TaskAction = 'retry' | 'approve' | 'skip';

const ACTION_LABELS: Record<TaskAction, { label: string; confirm: string }> = {
  retry: {
    label: 'Resetar tentativas',
    confirm: 'Zerar attempts e rejeições desta task? Squire vai retomá-la do zero.',
  },
  approve: {
    label: 'Aprovar manualmente',
    confirm: 'Marcar esta task como aprovada/completed sem passar pela homologação?',
  },
  skip: {
    label: 'Pular homologação',
    confirm: 'Marcar skip_homologation=true? A próxima rodada vai pular o review do Claude.',
  },
};

function TaskActionsMenu({
  task,
  projectId,
  onChanged,
  onEdit,
}: {
  task: Task;
  projectId: string;
  onChanged: () => void;
  onEdit: (task: Task) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<TaskAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    if (!window.confirm(`Excluir a task ${task.id} (${task.title})?`)) return;
    setError(null);
    try {
      const res = await authedFetch(
        `/api/projects/${projectId}/tasks/${task.id}`,
        { method: 'DELETE' }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.error ?? 'request_failed');
      }
      setOpen(false);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const fire = async (action: TaskAction) => {
    if (!window.confirm(ACTION_LABELS[action].confirm)) return;
    setPending(action);
    setError(null);
    try {
      const res = await authedFetch(
        `/api/projects/${projectId}/tasks/${task.id}/action`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.error ?? 'request_failed');
      }
      setOpen(false);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="text-gray-400 hover:text-gray-700 px-2 rounded"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Ações da task"
      >
        ⋯
      </button>
      {open && (
        <div
          className="absolute right-0 mt-1 w-56 bg-white border border-gray-200 rounded-md shadow-lg z-20 py-1 text-left"
          onClick={(e) => e.stopPropagation()}
          role="menu"
        >
          {(Object.keys(ACTION_LABELS) as TaskAction[]).map((action) => (
            <button
              key={action}
              onClick={() => fire(action)}
              disabled={pending !== null}
              className="block w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              role="menuitem"
            >
              {ACTION_LABELS[action].label}
              {pending === action && '…'}
            </button>
          ))}
          <div className="my-1 border-t border-gray-100" />
          <button
            onClick={() => {
              setOpen(false);
              onEdit(task);
            }}
            className="block w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            role="menuitem"
          >
            Editar task
          </button>
          <button
            onClick={remove}
            className="block w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            role="menuitem"
          >
            Excluir task
          </button>
          {error && (
            <div className="px-3 py-1 text-xs text-red-700 border-t border-gray-100">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const getEffortLabel = (effort: string) => {
  switch (effort) {
    case 'low': return 'baixo';
    case 'medium': return 'médio';
    case 'high': return 'alto';
    default: return effort;
  }
};

const getEffortColor = (effort: string) => {
  switch (effort) {
    case 'low': return 'text-gray-600 bg-gray-50';
    case 'medium': return 'text-blue-600 bg-blue-50';
    case 'high': return 'text-orange-600 bg-orange-50';
    default: return 'text-gray-600 bg-gray-50';
  }
};

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed': return 'text-green-600 bg-green-50';
    case 'implementing': return 'text-blue-600 bg-blue-50';
    case 'testing': return 'text-yellow-600 bg-yellow-50';
    case 'homologating': return 'text-purple-600 bg-purple-50';
    case 'blocked': return 'text-red-600 bg-red-50';
    default: return 'text-gray-600 bg-gray-50';
  }
};

const getHomologationLabel = (result: string | null) => {
  switch (result) {
    case 'approved': return { label: 'Aprovado', color: 'text-green-600' };
    case 'rejected': return { label: 'Reprovado', color: 'text-red-600' };
    case 'pending': return { label: 'Pendente', color: 'text-gray-600' };
    default: return null;
  }
};

export default function TaskList({ tasks, projectId }: TaskListProps) {
  const router = useRouter();
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());
  const [formTask, setFormTask] = useState<Task | null>(null);
  const [creating, setCreating] = useState(false);

  const toggleExpand = (taskId: string) => {
    const newExpanded = new Set(expandedTasks);
    if (newExpanded.has(taskId)) {
      newExpanded.delete(taskId);
    } else {
      newExpanded.add(taskId);
    }
    setExpandedTasks(newExpanded);
  };

  return (
    <div className="space-y-4">
      {projectId && (
        <div className="flex justify-end">
          <button
            onClick={() => setCreating(true)}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
          >
            + Nova task
          </button>
        </div>
      )}
      {projectId && creating && (
        <TaskForm projectId={projectId} onClose={() => setCreating(false)} />
      )}
      {projectId && formTask && (
        <TaskForm
          projectId={projectId}
          task={formTask}
          onClose={() => setFormTask(null)}
        />
      )}
      {tasks.map((task, index) => (
        <div
          key={task.id}
          className="border border-gray-200 rounded-lg overflow-hidden transition-all duration-200 hover:shadow-md"
        >
          <div
            className="p-4 flex items-center justify-between cursor-pointer bg-gray-50 hover:bg-gray-100"
            onClick={() => toggleExpand(task.id)}
          >
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${
                task.status === 'completed' ? 'bg-green-500' :
                task.status === 'blocked' ? 'bg-red-500' :
                'bg-blue-500'
              }`} />
              <h3 className="font-semibold text-gray-800">
                <span className="text-gray-400 font-mono text-xs mr-1">#{index + 1}</span>
                {task.title}
              </h3>
            </div>

            <div className="flex items-center gap-2 text-sm flex-wrap justify-end">
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(task.status)}`}>
                {task.status}
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${getEffortColor(task.effort)}`}>
                {getEffortLabel(task.effort)}
              </span>
              {task.tdd && (
                <span className="flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-yellow-700 bg-yellow-50">
                  <svg role="img" className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  {task.test_author}
                </span>
              )}
              {task.skip_homologation && (
                <span
                  className="px-2 py-0.5 rounded text-xs font-medium text-indigo-700 bg-indigo-50"
                  title="Auto-aprovada após inner loop (sem review do Claude Code)"
                >
                  fast-track
                </span>
              )}
              {(task.cost_usd > 0 || (task.max_usd ?? 0) > 0) && (
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium font-mono ${
                    task.max_usd && task.cost_usd >= task.max_usd
                      ? 'text-red-700 bg-red-50'
                      : 'text-gray-700 bg-gray-100'
                  }`}
                  title="Custo gasto / cap da task"
                >
                  ${task.cost_usd.toFixed(2)}
                  {task.max_usd && task.max_usd > 0
                    ? ` / $${task.max_usd.toFixed(2)}`
                    : ''}
                </span>
              )}
              {task.rejection_summaries.length > 0 && (
                <span className="px-2 py-0.5 rounded text-xs font-medium text-red-700 bg-red-50">
                  {task.rejection_summaries.length === 1
                    ? '1 rejeição'
                    : `${task.rejection_summaries.length} rejeições`}
                </span>
              )}
              {task.no_progress_streak >= 2 && task.no_progress_streak < 3 && (
                <span
                  className="px-2 py-0.5 rounded text-xs font-medium text-amber-700 bg-amber-50"
                  title="Nenhum arquivo modificado nos últimos ciclos"
                >
                  Sem progresso ({task.no_progress_streak})
                </span>
              )}
              {task.no_progress_streak >= 3 && (
                <span
                  className="px-2 py-0.5 rounded text-xs font-medium text-red-700 bg-red-100"
                  title="Loop detectado — escalação iminente"
                >
                  Loop ({task.no_progress_streak} ciclos)
                </span>
              )}
              <button className="text-gray-400 hover:text-gray-600 ml-2">
                {expandedTasks.has(task.id) ? '▲' : '▼'}
              </button>
              {projectId && (
                <TaskActionsMenu
                  task={task}
                  projectId={projectId}
                  onChanged={() => router.refresh()}
                  onEdit={(t) => setFormTask(t)}
                />
              )}
            </div>
          </div>

          {expandedTasks.has(task.id) && (
            <div className="p-4 bg-white border-t border-gray-100">
              <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-500">Tentativas:</span>
                  <span className="text-gray-800 font-mono">{task.attempts}</span>
                </div>
                {task.homologation_result !== null && (() => {
                  const hom = getHomologationLabel(task.homologation_result);
                  return hom ? (
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-500">Homologação:</span>
                      <span className={`font-medium ${hom.color}`}>{hom.label}</span>
                    </div>
                  ) : null;
                })()}
              </div>

              {task.rejection_summaries.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    Rejeições
                  </h4>
                  <ul className="space-y-1">
                    {task.rejection_summaries.map((summary, i) => (
                      <li key={i} className="text-sm text-gray-700">{summary}</li>
                    ))}
                  </ul>
                </div>
              )}

              {task.subtasks.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    Subtarefas
                  </h4>
                  <ul className="space-y-2">
                    {task.subtasks.map((subtask) => (
                      <li key={subtask.id} className="flex items-center gap-2 text-sm">
                        <div className={`w-2 h-2 rounded-full ${
                          subtask.status === 'completed' ? 'bg-green-400' : 'bg-gray-300'
                        }`} />
                        <span className={subtask.status === 'completed' ? 'text-gray-600 line-through' : 'text-gray-800'}>
                          {subtask.title}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
