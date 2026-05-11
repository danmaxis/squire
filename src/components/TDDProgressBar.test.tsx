import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TDDProgressBar } from './TDDProgressBar';
import type { Task, Cursor, LLMContextSummary } from '@/lib/types';

const baseTask: Task = {
  id: 'task-1',
  title: 'Test Task',
  description: 'A test task',
  status: 'implementing',
  assigned_to: 'claude_code',
  attempts: 1,
  max_attempts: 3,
  homologation_result: null,
  homologation_attempt: 0,
  max_homologation_attempts: 2,
  completed_at: null,
  claude_code_assisted: true,
  subtasks: [],
  rejection_summaries: [],
  no_progress_streak: 0,
  skip_homologation: false,
  effort: 'medium',
  tdd: true,
  test_author: 'claude',
  max_usd: null,
  cost_usd: 0,
};

const baseCursor: Cursor = {
  current_task_id: 'task-1',
  current_subtask_id: null,
  step: 'planning',
  attempt: 1,
  homologation_attempt: 0,
};

const baseLLMContext: LLMContextSummary = {
  last_instruction: 'test',
  files_touched: [],
  last_error: null,
  tests_passing: 0,
  tests_failing: 0,
  test_summary: '',
};

describe('TDDProgressBar', () => {
  it('returns null when task.tdd is false', () => {
    const { container } = render(
      <TDDProgressBar task={{ ...baseTask, tdd: false }} cursor={baseCursor} llm_context={baseLLMContext} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('returns null when cursor.current_task_id !== task.id', () => {
    const { container } = render(
      <TDDProgressBar task={baseTask} cursor={{ ...baseCursor, current_task_id: 'other-task' }} llm_context={baseLLMContext} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders all 6 steps with PT-BR labels', () => {
    const { container } = render(
      <TDDProgressBar task={baseTask} cursor={{ ...baseCursor, step: 'completed' }} llm_context={baseLLMContext} />
    );
    const expectedLabels = ['Planejamento', 'RED (testes)', 'Implementação', 'Rodando testes', 'Homologação', 'Concluído'];
    expectedLabels.forEach((label) => {
      expect(container.textContent).toContain(label);
    });
  });

  it('current step has ring and bold label', () => {
    const { container } = render(
      <TDDProgressBar task={baseTask} cursor={{ ...baseCursor, step: 'testing' }} llm_context={baseLLMContext} />
    );
    const testingStep = container.querySelector('div:nth-child(4)');
    expect(testingStep?.querySelector('.ring-4')).toBeTruthy();
    expect(testingStep?.querySelector('span')).toHaveTextContent('Rodando testes');
  });

  it('red_phase shows test_author extra info', () => {
    const { container } = render(
      <TDDProgressBar task={{ ...baseTask, test_author: 'claude' }} cursor={{ ...baseCursor, step: 'red_phase' }} llm_context={baseLLMContext} />
    );
    expect(container.textContent).toContain('Claude');
  });

  it('llm_execution shows Tentativa N/M', () => {
    const { container } = render(
      <TDDProgressBar task={baseTask} cursor={{ ...baseCursor, step: 'llm_execution', attempt: 2 }} llm_context={baseLLMContext} />
    );
    expect(container.textContent).toContain('Tentativa 2/3');
  });

  it('testing shows N passing, M failing', () => {
    const { container } = render(
      <TDDProgressBar task={baseTask} cursor={{ ...baseCursor, step: 'testing' }} llm_context={{ ...baseLLMContext, tests_passing: 5, tests_failing: 2 }} />
    );
    expect(container.textContent).toContain('5 passando, 2 falhando');
  });

  it('homologation shows Homologação N/M', () => {
    const { container } = render(
      <TDDProgressBar task={baseTask} cursor={{ ...baseCursor, step: 'homologation', homologation_attempt: 1 }} llm_context={baseLLMContext} />
    );
    expect(container.textContent).toContain('Homologação 1/2');
  });
});
