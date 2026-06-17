import { join } from 'path';

export const DATA_PATH =
  process.env.SQUIRE_DATA_PATH ?? join(process.cwd(), 'fixtures', 'data');

export const alertsPath = () => join(DATA_PATH, 'alerts.json');
export const projectPath = (id: string) => join(DATA_PATH, 'projects', id);
export const projectJsonPath = (id: string) =>
  join(projectPath(id), 'project.json');
export const tasksPath = (id: string) => join(projectPath(id), 'tasks.json');
export const checkpointPath = (id: string) =>
  join(projectPath(id), 'checkpoint.json');
