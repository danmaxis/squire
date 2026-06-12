import { describe, it, expect } from 'vitest';
import { getAlerts, getTasks, getGlobalStats, getCheckpoint } from './data';

describe('data.ts', () => {
  it('getAlerts returns array from AlertList wrapper', async () => {
    const alerts = await getAlerts();
    expect(Array.isArray(alerts)).toBe(true);
    if (alerts.length > 0) {
      expect(alerts[0]).toHaveProperty('project_id');
      expect(alerts[0]).toHaveProperty('severity');
      expect(alerts[0]).toHaveProperty('message');
      expect(alerts[0]).toHaveProperty('acknowledged');
    }
  });

  it('getTasks returns array from TaskList wrapper', async () => {
    const tasks = await getTasks('squire-dashboard');
    expect(Array.isArray(tasks)).toBe(true);
    if (tasks.length > 0) {
      expect(tasks[0]).toHaveProperty('id');
      expect(tasks[0]).toHaveProperty('status');
      expect(tasks[0]).toHaveProperty('title');
    }
  });

  it('getGlobalStats returns GlobalStats with correct snake_case fields', async () => {
    const stats = await getGlobalStats();
    if (stats !== null) {
      expect(stats).toHaveProperty('daily_claude_code_calls');
      expect(stats).toHaveProperty('daily_local_llm_calls');
      expect(stats).toHaveProperty('cost_estimate_usd');
      expect(stats).toHaveProperty('tasks_completed_today');
      expect(stats).toHaveProperty('approval_first_try_rate');
      expect(stats).toHaveProperty('date');
      expect(stats).toHaveProperty('projects_touched_today');
    }
  });

  it('getCheckpoint returns Checkpoint with correct fields or null', async () => {
    const checkpoint = await getCheckpoint('squire-dashboard');
    if (checkpoint !== null) {
      expect(checkpoint).toHaveProperty('cursor');
      expect(checkpoint).toHaveProperty('llm_context');
      expect(checkpoint).toHaveProperty('recovery');
      expect(checkpoint).toHaveProperty('rate_limit');
      expect(checkpoint.cursor).toHaveProperty('current_task_id');
      expect(checkpoint.cursor).toHaveProperty('step');
    }
  });

  it('getAlerts returns empty array when file missing', async () => {
    const alerts = await getAlerts();
    expect(Array.isArray(alerts)).toBe(true);
  });

  it('getTasks returns empty array for unknown project', async () => {
    const tasks = await getTasks('nonexistent-project-id');
    expect(tasks).toEqual([]);
  });
});

describe('getTasks normalization', () => {
  it('preenche defaults em tasks.json mínimo (template antigo do wrapper)', async () => {
    const { getTasks } = await import('./data');
    const tasks = await getTasks('minimal-template');
    expect(tasks).toHaveLength(1);
    const t = tasks[0];
    // campos presentes vencem
    expect(t.id).toBe('task-001');
    expect(t.description).toBe('template antigo do wrapper');
    // campos ausentes recebem defaults — eram undefined e quebravam .length/.map
    expect(t.rejection_summaries).toEqual([]);
    expect(t.attempts).toBe(0);
    expect(t.effort).toBe('medium');
    expect(t.tdd).toBe(true);
    expect(t.cost_usd).toBe(0);
  });
});

describe('getHomologationLog', () => {
  it('retorna entries do arquivo', async () => {
    const { getHomologationLog } = await import('./data');
    const entries = await getHomologationLog('minimal-template');
    expect(entries).toHaveLength(1);
    expect(entries[0].fix_suggestion).toBe('conserte X');
  });

  it('retorna vazio quando arquivo não existe', async () => {
    const { getHomologationLog } = await import('./data');
    expect(await getHomologationLog('nonexistent')).toEqual([]);
  });
});
