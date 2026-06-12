import { promises as fs } from 'fs';
import { join } from 'path';
import { newTask } from './taskDefaults';
import type {
  Project,
  Task,
  HistoryEvent,
  CommitSummary,
  Alert,
  GlobalStats,
  Checkpoint,
  AlertList,
  TaskList,
  History,
  CommitLog,
} from './types';

const DATA_PATH =
  process.env.SQUIRE_DATA_PATH ?? join(process.cwd(), 'fixtures', 'data');

async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}

export async function getProjects(): Promise<Project[]> {
  try {
    const projectsDir = join(DATA_PATH, 'projects');
    const stats = await fs.stat(projectsDir);
    if (!stats.isDirectory()) {
      return [];
    }

    const entries = await fs.readdir(projectsDir, { withFileTypes: true });
    const projectPaths: string[] = [];

    for (const entry of entries) {
      if (entry.isDirectory()) {
        const projectJsonPath = join(projectsDir, entry.name, 'project.json');
        try {
          await fs.access(projectJsonPath);
          projectPaths.push(projectJsonPath);
        } catch {
          continue;
        }
      }
    }

    const results = await Promise.all(
      projectPaths.map((path) => readJsonFile<Project>(path))
    );
    return results.filter((p): p is Project => p !== null);
  } catch {
    return [];
  }
}

export async function getProject(id: string): Promise<Project | null> {
  const projectJsonPath = join(DATA_PATH, 'projects', id, 'project.json');
  return readJsonFile<Project>(projectJsonPath);
}

export async function getTasks(projectId: string): Promise<Task[]> {
  const tasksPath = join(DATA_PATH, 'projects', projectId, 'tasks.json');
  const data = await readJsonFile<TaskList>(tasksPath);
  // Normaliza contra tasks.json mínimos (templates antigos / edição manual):
  // campos ausentes recebem os defaults do modelo Python, presentes vencem.
  return (data?.tasks ?? []).map(
    (raw) =>
      ({
        ...newTask({ id: raw.id ?? '', title: raw.title ?? '' }),
        ...raw,
      }) as Task
  );
}

export async function getHistory(projectId: string): Promise<HistoryEvent[]> {
  const historyPath = join(DATA_PATH, 'projects', projectId, 'history.json');
  const data = await readJsonFile<History>(historyPath);
  return data?.events ?? [];
}

export async function getCommits(projectId: string): Promise<CommitSummary[]> {
  const commitsPath = join(DATA_PATH, 'projects', projectId, 'commits.json');
  const data = await readJsonFile<CommitLog>(commitsPath);
  return data?.commits ?? [];
}

export async function getAlerts(): Promise<Alert[]> {
  const alertsPath = join(DATA_PATH, 'alerts.json');
  const data = await readJsonFile<AlertList>(alertsPath);
  return data?.alerts ?? [];
}

export async function getGlobalStats(): Promise<GlobalStats | null> {
  const globalStatsPath = join(DATA_PATH, 'global-stats.json');
  return readJsonFile<GlobalStats>(globalStatsPath);
}

export async function getCheckpoint(projectId: string): Promise<Checkpoint | null> {
  const checkpointPath = join(DATA_PATH, 'projects', projectId, 'checkpoint.json');
  return readJsonFile<Checkpoint>(checkpointPath);
}
