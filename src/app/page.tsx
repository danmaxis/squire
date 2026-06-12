import { Suspense } from 'react';
import { promises as fs } from 'fs';
import { join } from 'path';
import Link from 'next/link';

import { ProjectCard } from '@/components/ProjectCard';
import AlertBanner from '@/components/AlertBanner';
import GlobalStats from '@/components/GlobalStats';
import BudgetCard from '@/components/BudgetCard';
import { RefreshController } from '@/components/RefreshController';
import { getCheckpoint } from '@/lib/data';
import type { Alert, RateLimitState } from '@/lib/types';

// A página lê o estado do squire no filesystem a cada request — sem isto o
// Next prerenderiza estático no build (que roda SEM o volume de dados) e a
// home mostra para sempre o snapshot vazio do build.
export const dynamic = 'force-dynamic';

const DATA_PATH = process.env.SQUIRE_DATA_PATH ?? join(process.cwd(), 'fixtures', 'data');

interface ProjectJson {
  id: string;
  name: string;
  description: string;
  status: string;
  updated_at: string;
}

interface TaskJson {
  id: string;
  status: string;
}


async function readJson<T>(path: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(path, 'utf-8');
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function getProjectsWithProgress() {
  const projectsDir = join(DATA_PATH, 'projects');
  let entries: string[] = [];
  try {
    const dirents = await fs.readdir(projectsDir, { withFileTypes: true });
    entries = dirents.filter((d) => d.isDirectory()).map((d) => d.name);
  } catch {
    return [];
  }

  const results = await Promise.all(
    entries.map(async (name) => {
      const project = await readJson<ProjectJson>(join(projectsDir, name, 'project.json'));
      if (!project) return null;

      const tasksData = await readJson<{ tasks: TaskJson[] } | TaskJson[]>(
        join(projectsDir, name, 'tasks.json')
      );
      const tasks: TaskJson[] = Array.isArray(tasksData)
        ? tasksData
        : (tasksData as { tasks: TaskJson[] })?.tasks ?? [];

      const completed = tasks.filter((t) => t.status === 'completed').length;
      return { project, tasks, completedTasks: completed };
    })
  );

  return results.filter(Boolean) as {
    project: ProjectJson;
    tasks: TaskJson[];
    completedTasks: number;
  }[];
}

async function getAlerts(): Promise<Alert[]> {
  const wrapper = await readJson<{ alerts: Alert[] }>(join(DATA_PATH, 'alerts.json'));
  return wrapper?.alerts ?? [];
}

function mapStatus(status: string): 'active' | 'completed' | 'on-hold' | 'failed' {
  if (status === 'implementing' || status === 'planning') return 'active';
  if (status === 'completed') return 'completed';
  if (status === 'paused' || status === 'blocked') return 'on-hold';
  if (status === 'failed') return 'failed';
  return 'active';
}

async function getGlobalStatsData() {
  const stats = await readJson<import('@/lib/types').GlobalStats>(join(DATA_PATH, 'global-stats.json'));
  return stats ?? null;
}

async function getRateLimits(
  projectIds: string[]
): Promise<Array<{ project_id: string; rate_limit: RateLimitState }>> {
  const checkpoints = await Promise.all(
    projectIds.map(async (id) => {
      const cp = await getCheckpoint(id);
      return cp ? { project_id: id, rate_limit: cp.rate_limit } : null;
    })
  );
  return checkpoints.filter(
    (c): c is { project_id: string; rate_limit: RateLimitState } => c !== null
  );
}

export default async function HomePage() {
  const [projectData, alerts, stats] = await Promise.all([
    getProjectsWithProgress(),
    getAlerts(),
    getGlobalStatsData(),
  ]);
  const rateLimits = await getRateLimits(
    projectData.map(({ project }) => project.id)
  );

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Barra de alertas no topo */}
      {alerts.length > 0 && <AlertBanner alerts={alerts} />}

      <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 ${alerts.length > 0 ? 'pt-24' : ''}`}>
        {/* Cabeçalho */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Squire Dashboard
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {projectData.length} projeto{projectData.length !== 1 ? 's' : ''} monitorado
              {projectData.length !== 1 ? 's' : ''}
            </p>
          </div>

          {/* Indicador de auto-refresh — client component */}
          <Suspense fallback={null}>
            <RefreshController />
          </Suspense>
        </div>

        {/* Métricas globais + budget */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <div className="lg:col-span-2">
            <GlobalStats stats={stats} />
          </div>
          <div>
            <BudgetCard stats={stats} rateLimits={rateLimits} />
          </div>
        </div>

        {/* Lista de projetos */}
        {projectData.length === 0 ? (
          <div className="text-center py-16 text-gray-400 dark:text-gray-500">
            <p className="text-lg">Nenhum projeto encontrado.</p>
            <p className="text-sm mt-2">
              Verifique se <code className="font-mono">SQUIRE_DATA_PATH</code> aponta para o
              diretório correto.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projectData.map(({ project, tasks, completedTasks }) => (
              <Link key={project.id} href={`/projects/${project.id}`} className="block">
                <ProjectCard
                  id={project.id}
                  name={project.name}
                  description={project.description}
                  status={mapStatus(project.status)}
                  completedTasks={completedTasks}
                  totalTasks={tasks.length}
                  lastUpdated={new Date(project.updated_at)}
                />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
