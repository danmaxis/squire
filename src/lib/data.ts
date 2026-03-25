import { promises as fs } from 'fs';
import { join } from 'path';

// Define o caminho base a partir da variável de ambiente ou usa um padrão para desenvolvimento
const DATA_PATH = process.env.ORCHESTRATOR_DATA_PATH || './data';

// Tipos de dados baseados na estrutura esperada
export interface Project {
  id: string;
  name: string;
  status: 'active' | 'paused' | 'completed';
  createdAt: string;
  updatedAt: string;
}

export interface Task {
  id: string;
  projectId: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startedAt?: string;
  completedAt?: string;
  logs?: string[];
}

export interface HistoryEvent {
  id: string;
  projectId: string;
  timestamp: string;
  type: 'start' | 'stop' | 'error' | 'update';
  message: string;
}

export interface CommitSummary {
  id: string;
  projectId: string;
  commitHash: string;
  author: string;
  message: string;
  timestamp: string;
}

export interface Alert {
  id: string;
  projectId?: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

export interface GlobalStats {
  totalProjects: number;
  activeProjects: number;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  totalAlerts: number;
  criticalAlerts: number;
}

/**
 * Helper para ler e parsear um arquivo JSON com tratamento de erro robusto.
 * Retorna null se o arquivo não existir ou estiver inválido.
 */
async function readJsonFile<T>(filePath: string): Promise<T | null> {
  try {
    const data = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(data) as T;
  } catch (error) {
    // Se o arquivo não existir ou for inválido, retorna null
    // O caller deve tratar o null retornando defaults
    return null;
  }
}

/**
 * Helper para ler múltiplos arquivos JSON de uma lista de paths.
 */
async function readJsonFiles<T>(filePaths: string[]): Promise<T[]> {
  const results = await Promise.all(filePaths.map(readJsonFile<T>));
  return results.filter((item): item is NonNullable<typeof item> => item !== null) as T[];
}

/**
 * Lista todos os projetos disponíveis no diretório de dados.
 * Assume que cada projeto está em uma subpasta com um arquivo project.json.
 */
export async function getProjects(): Promise<Project[]> {
  try {
    // Verifica se o diretório base existe
    const stats = await fs.stat(DATA_PATH);
    if (!stats.isDirectory()) {
      return [];
    }

    // Lista diretórios no caminho base
    const entries = await fs.readdir(DATA_PATH, { withFileTypes: true });
    
    const projectPaths: string[] = [];
    
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const projectJsonPath = join(DATA_PATH, entry.name, 'project.json');
        // Verifica se o arquivo project.json existe antes de adicionar ao array de leitura
        try {
          await fs.access(projectJsonPath);
          projectPaths.push(projectJsonPath);
        } catch {
          // Arquivo não encontrado neste diretório, ignora
          continue;
        }
      }
    }

    return readJsonFiles<Project>(projectPaths);
  } catch (error) {
    // Se o diretório base não existir, retorna array vazio
    return [];
  }
}

/**
 * Obtém um projeto específico pelo ID.
 */
export async function getProject(id: string): Promise<Project | null> {
  const projectJsonPath = join(DATA_PATH, id, 'project.json');
  const project = await readJsonFile<Project>(projectJsonPath);
  return project;
}

/**
 * Obtém todas as tarefas de um projeto específico.
 * Assume que as tarefas estão em tasks.json dentro da pasta do projeto.
 */
export async function getTasks(projectId: string): Promise<Task[]> {
  const tasksPath = join(DATA_PATH, projectId, 'tasks.json');
  const tasks = await readJsonFile<Task[]>(tasksPath);
  return tasks || [];
}

/**
 * Obtém o histórico de eventos de um projeto.
 */
export async function getHistory(projectId: string): Promise<HistoryEvent[]> {
  const historyPath = join(DATA_PATH, projectId, 'history.json');
  const history = await readJsonFile<HistoryEvent[]>(historyPath);
  return history || [];
}

/**
 * Obtém o resumo de commits de um projeto.
 */
export async function getCommits(projectId: string): Promise<CommitSummary[]> {
  const commitsPath = join(DATA_PATH, projectId, 'commits.json');
  const commits = await readJsonFile<CommitSummary[]>(commitsPath);
  return commits || [];
}

/**
 * Obtém todas as alertas globais.
 * Assume que os alertas estão em alerts.json na raiz do DATA_PATH.
 */
export async function getAlerts(): Promise<Alert[]> {
  const alertsPath = join(DATA_PATH, 'alerts.json');
  const alerts = await readJsonFile<Alert[]>(alertsPath);
  return alerts || [];
}

/**
 * Calcula e retorna as estatísticas globais do sistema.
 */
export async function getGlobalStats(): Promise<GlobalStats> {
  const projects = await getProjects();
  const alerts = await getAlerts();
  
  let totalTasks = 0;
  let completedTasks = 0;
  let failedTasks = 0;

  // Itera sobre cada projeto para somar estatísticas de tarefas
  for (const project of projects) {
    const tasks = await getTasks(project.id);
    totalTasks += tasks.length;
    completedTasks += tasks.filter(t => t.status === 'completed').length;
    failedTasks += tasks.filter(t => t.status === 'failed').length;
  }

  return {
    totalProjects: projects.length,
    activeProjects: projects.filter(p => p.status === 'active').length,
    totalTasks,
    completedTasks,
    failedTasks,
    totalAlerts: alerts.length,
    criticalAlerts: alerts.filter(a => a.severity === 'critical').length,
  };
}