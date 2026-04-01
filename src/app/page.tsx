import { Suspense } from 'react';
import { promises as fs } from 'fs';
import { join } from 'path';
import Link from 'next/link';

import { ProjectCard } from '@/components/ProjectCard';
import AlertBanner from '@/components/AlertBanner';
import GlobalStats from '@/components/GlobalStats';
import { RefreshController } from '@/components/RefreshController';

const DATA_PATH = process.env.ORCHESTRATOR_DATA_PATH ?? join(process.cwd(), 'fixtures', 'data');

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

interface AlertJson {
  id: string;
  severity: 'critical' | 'warning';
  project: string;
  task: string;
  message: string;
  created_at: string;
  acknowledged: boolean;
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

async function getAlerts(): Promise<AlertJson[]> {
  const wrapper = await readJson<{ alerts: AlertJson[] }>(join(DATA_PATH, 'alerts.json'));
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

export default async function HomePage() {
  const [projectData, alerts, stats] = await Promise.all([
    getProjectsWithProgress(),
    getAlerts(),
    getGlobalStatsData(),
  ]);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Barra de alertas no topo */}
      {alerts.length > 0 && <AlertBanner alerts={alerts} />}

      <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 ${alerts.length > 0 ? 'pt-24' : ''}`}>
        {/* Cabeçalho */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Orchestrator Dashboard
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

        {/* Métricas globais */}
        <GlobalStats stats={stats} />

        {/* Lista de projetos */}
        {projectData.length === 0 ? (
          <div className="text-center py-16 text-gray-400 dark:text-gray-500">
            <p className="text-lg">Nenhum projeto encontrado.</p>
            <p className="text-sm mt-2">
              Verifique se <code className="font-mono">ORCHESTRATOR_DATA_PATH</code> aponta para o
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
