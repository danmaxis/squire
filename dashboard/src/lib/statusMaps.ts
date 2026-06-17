import type { CursorStep, ProjectStatus, TaskStatus } from './types';

/**
 * Labels PT centralizados para os enums do squire — única fonte para
 * sidebar, cards, chips e painéis (antes cada componente tinha o seu,
 * alguns em inglês, outros mostrando o enum cru).
 */

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: 'Planejamento',
  implementing: 'Implementando',
  reviewing: 'Revisão',
  blocked: 'Bloqueado',
  completed: 'Concluído',
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: 'pendente',
  implementing: 'implementando',
  testing: 'testando',
  homologating: 'homologando',
  completed: 'concluída',
  blocked: 'bloqueada',
};

export const CURSOR_STEP_LABELS: Record<CursorStep, string> = {
  planning: 'planejamento',
  red_phase: 'teste (RED)',
  llm_execution: 'execução LLM',
  testing: 'testes',
  homologation: 'homologação',
  completed: 'concluído',
};
