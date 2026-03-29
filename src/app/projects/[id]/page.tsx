import { notFound } from 'next/navigation';
import Link from 'next/link';
import { getProject, getTasks, getHistory, getCommits, getCheckpoint } from '@/lib/data';
import TaskList from '@/components/TaskList';
import { Timeline } from '@/components/Timeline';
import { CommitLog } from '@/components/CommitLog';
import { CheckpointPanel } from '@/components/CheckpointPanel';
import type { ProjectStatus } from '@/lib/types';

const statusColors: Record<ProjectStatus, string> = {
  planning:     'bg-gray-100 text-gray-700',
  implementing: 'bg-blue-100 text-blue-700',
  reviewing:    'bg-yellow-100 text-yellow-700',
  blocked:      'bg-red-100 text-red-700',
  completed:    'bg-green-100 text-green-700',
};

const statusLabels: Record<ProjectStatus, string> = {
  planning:     'Planejamento',
  implementing: 'Implementando',
  reviewing:    'Revisão',
  blocked:      'Bloqueado',
  completed:    'Concluído',
};

export default async function ProjectPage({ params }: { params: { id: string } }) {
  const { id } = params;

  const [project, tasks, history, commits, checkpoint] = await Promise.all([
    getProject(id),
    getTasks(id),
    getHistory(id),
    getCommits(id),
    getCheckpoint(id),
  ]);

  if (!project) notFound();

  const status = project.status as ProjectStatus;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <Link href="/" className="text-sm text-blue-500 hover:underline mb-1 block">
              ← Todos os projetos
            </Link>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{project.name}</h1>
            <p className="text-sm text-gray-500 mt-1">{project.description}</p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-semibold ${statusColors[status] ?? 'bg-gray-100 text-gray-700'}`}>
            {statusLabels[status] ?? status}
          </span>
        </div>

        {/* Checkpoint panel (full width) */}
        {checkpoint && <CheckpointPanel checkpoint={checkpoint} />}

        {/* Main content: tasks + timeline */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Tasks ({tasks.length})
            </h2>
            <TaskList tasks={tasks} />
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Histórico
            </h2>
            <Timeline events={history} />
          </div>
        </div>

        {/* Commit log */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Commits</h2>
          <CommitLog commits={commits} />
        </div>

      </div>
    </div>
  );
}
