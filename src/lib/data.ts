import { promises as fs } from 'fs';
import { join } from 'path';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);
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
  process.env.ORCHESTRATOR_DATA_PATH ?? join(process.cwd(), 'fixtures', 'data');

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
  return data?.tasks ?? [];
}

export async function getHistory(projectId: string): Promise<HistoryEvent[]> {
  const historyPath = join(DATA_PATH, 'projects', projectId, 'history.json');
  const data = await readJsonFile<History>(historyPath);
  return data?.events ?? [];
}

async function getCommitsFromGit(repoPath: string): Promise<CommitSummary[]> {
  try {
    // Formato: linha HEADER seguida de arquivos alterados, separados por COMMITSEP
    const { stdout } = await execAsync(
      'git log -n 100 --format=COMMITSEP%n%H%n%s%n%aI --name-only',
      { cwd: repoPath, timeout: 5000 }
    );

    const commits: CommitSummary[] = [];
    // Divide nos blocos de cada commit
    const blocks = stdout.split('\nCOMMITSEP\n').filter((b) => b.trim());

    for (const block of blocks) {
      const lines = block.replace(/^COMMITSEP\n/, '').split('\n');
      const [sha, message, timestamp, ...rest] = lines;
      if (!sha || !message || !timestamp) continue;
      const files_changed = rest.filter((l) => l.trim() !== '');
      commits.push({
        sha,
        message,
        timestamp,
        diff_summary: `${files_changed.length} arquivo(s) alterado(s)`,
        files_changed,
      });
    }

    return commits;
  } catch {
    return [];
  }
}

export async function getCommits(projectId: string): Promise<CommitSummary[]> {
  // Tenta commits.json primeiro (squire pode gerar no futuro)
  const commitsPath = join(DATA_PATH, 'projects', projectId, 'commits.json');
  const data = await readJsonFile<CommitLog>(commitsPath);
  if (data?.commits && data.commits.length > 0) return data.commits;

  // Fallback: lê git log direto do repo_path do projeto
  const project = await getProject(projectId);
  if (project?.repo_path) return getCommitsFromGit(project.repo_path);

  return [];
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
