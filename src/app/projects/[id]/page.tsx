import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  getProject,
  getTasks,
  getHistory,
  getCommits,
  getCheckpoint,
  getHomologationLog,
} from '@/lib/data';
import TaskList from '@/components/TaskList';
import { Timeline } from '@/components/Timeline';
import { CommitLog } from '@/components/CommitLog';
import { CheckpointPanel } from '@/components/CheckpointPanel';
import ProjectSettings from '@/components/ProjectSettings';
import PlanTasksPanel from '@/components/PlanTasksPanel';
import RunControls from '@/components/RunControls';
import { readSessionLock } from '@/lib/squireLock';
import { TDDProgressBar } from '@/components/TDDProgressBar';
import { RefreshController } from '@/components/RefreshController';
import { PROJECT_STATUS_LABELS } from '@/lib/statusMaps';
import type { ProjectStatus } from '@/lib/types';

const statusColors: Record<ProjectStatus, string> = {
  planning:     'bg-gray-100 text-gray-700',
  implementing: 'bg-blue-100 text-blue-700',
  reviewing:    'bg-yellow-100 text-yellow-700',
  blocked:      'bg-red-100 text-red-700',
  completed:    'bg-green-100 text-green-700',
};



export default async function ProjectPage({ params }: { params: { id: string } }) {
  const { id } = params;

  const [project, tasks, history, commits, checkpoint, lock, homologationLog] =
    await Promise.all([
      getProject(id),
      getTasks(id),
      getHistory(id),
      getCommits(id),
      getCheckpoint(id),
      readSessionLock(),
      getHomologationLog(id),
    ]);

  if (!project) notFound();

  const status = project.status as ProjectStatus;
  const currentTask =
    checkpoint && checkpoint.cursor.current_task_id
      ? tasks.find((t) => t.id === checkpoint.cursor.current_task_id) ?? null
      : null;
  const showTDD =
    currentTask !== null &&
    checkpoint !== null &&
    currentTask.tdd === true &&
    (['red_phase', 'llm_execution', 'testing', 'homologation'] as const).includes(
      checkpoint.cursor.step as 'red_phase' | 'llm_execution' | 'testing' | 'homologation'
    );

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
          <div className="flex items-center gap-2 flex-wrap">
            <RunControls
              projectId={project.id}
              lock={{ held: lock.held, holder: lock.holder, projectId: lock.projectId }}
            />
            <RefreshController hot={checkpoint?.phase === 'implementing'} />
            {project.coding_backend && (
              <span
                className="px-2.5 py-1 rounded-full text-xs font-medium font-mono bg-gray-100 text-gray-700"
                title="Backend de coding usado neste projeto"
              >
                ⚙ {project.coding_backend}
              </span>
            )}
            <span className={`px-3 py-1 rounded-full text-sm font-semibold ${statusColors[status] ?? 'bg-gray-100 text-gray-700'}`}>
              {PROJECT_STATUS_LABELS[status] ?? status}
            </span>
          </div>
        </div>

        {/* Live TDD progress (only when a task is actively running) */}
        {showTDD && currentTask && checkpoint && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-4">
              Progresso TDD — {currentTask.title}
            </h2>
            <TDDProgressBar
              task={currentTask}
              cursor={checkpoint.cursor}
              llm_context={checkpoint.llm_context}
            />
          </div>
        )}

        {/* Checkpoint panel (full width) */}
        {checkpoint && <CheckpointPanel checkpoint={checkpoint} />}

        {/* Main content: tasks + timeline */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Tasks ({tasks.length})
            </h2>
            <TaskList
              tasks={tasks}
              projectId={project.id}
              logEntries={homologationLog}
            />
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Histórico
            </h2>
            <Timeline events={history} logEntries={homologationLog} />
          </div>
        </div>

        {/* Commit log */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Commits</h2>
          <CommitLog commits={commits} />
        </div>

        {/* Planejamento com Claude */}
        <PlanTasksPanel
          projectId={project.id}
          initialDescription={project.description}
        />

        {/* Configurações */}
        <ProjectSettings project={project} />

      </div>
    </div>
  );
}
