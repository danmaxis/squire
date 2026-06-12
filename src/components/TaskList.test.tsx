import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import TaskList from './TaskList';
import { Task } from '@/lib/types';

const createMockTask = (overrides: Partial<Task> = {}): Task => ({
  id: 'task-1',
  title: 'Implement feature',
  description: 'Test description',
  status: 'implementing',
  assigned_to: 'claude_code',
  attempts: 2,
  max_attempts: 5,
  homologation_result: null,
  homologation_attempt: 0,
  max_homologation_attempts: 3,
  completed_at: null,
  claude_code_assisted: false,
  subtasks: [],
  rejection_summaries: [],
  no_progress_streak: 0,
  skip_homologation: false,
  effort: 'medium',
  tdd: false,
  test_author: 'claude',
  max_usd: null,
  cost_usd: 0,
  ...overrides,
});

const createTaskWithId = (id: string, title: string, overrides: Partial<Task> = {}): Task => ({
  id,
  title,
  description: 'Test description',
  status: 'implementing',
  assigned_to: 'claude_code',
  attempts: 2,
  max_attempts: 5,
  homologation_result: null,
  homologation_attempt: 0,
  max_homologation_attempts: 3,
  completed_at: null,
  claude_code_assisted: false,
  subtasks: [],
  rejection_summaries: [],
  no_progress_streak: 0,
  skip_homologation: false,
  effort: 'medium',
  tdd: false,
  test_author: 'claude',
  max_usd: null,
  cost_usd: 0,
  ...overrides,
});

describe('TaskList', () => {
  it('exibe numeração sequencial (#1, #2, ...) antes do título de cada tarefa', () => {
    const tasks: Task[] = [
      createTaskWithId('task-1', 'Primeira Tarefa'),
      createTaskWithId('task-2', 'Segunda Tarefa'),
      createTaskWithId('task-3', 'Terceira Tarefa'),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.getByText('#1')).toBeInTheDocument();
    expect(screen.getByText('#2')).toBeInTheDocument();
    expect(screen.getByText('#3')).toBeInTheDocument();
  });

  it('renders effort badges with correct labels and colors', () => {
    const tasks: Task[] = [
      createMockTask({ effort: 'low', id: 'task-1' }),
      createMockTask({ effort: 'medium', id: 'task-2' }),
      createMockTask({ effort: 'high', id: 'task-3' }),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.getByText('baixo')).toBeInTheDocument();
    expect(screen.getByText('médio')).toBeInTheDocument();
    expect(screen.getByText('alto')).toBeInTheDocument();

    const baixoBadge = screen.getByText('baixo');
    const medioBadge = screen.getByText('médio');
    const altoBadge = screen.getByText('alto');

    expect(baixoBadge).toHaveClass('bg-gray-50');
    expect(medioBadge).toHaveClass('bg-blue-50');
    expect(altoBadge).toHaveClass('bg-orange-50');
  });

  it('renders TDD indicator with lock icon and test_author label', () => {
    const tasks: Task[] = [
      createTaskWithId('task-1', 'Feature A', { tdd: true, test_author: 'claude' }),
      createTaskWithId('task-2', 'Feature B', { tdd: true, test_author: 'local' }),
      createTaskWithId('task-3', 'Feature C', { tdd: false }),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.getByText('claude')).toBeInTheDocument();
    expect(screen.getByText('local')).toBeInTheDocument();

    const lockIcons = screen.getAllByRole('img');
    expect(lockIcons.length).toBe(2);

    const featureCTask = screen.getByText('Feature C').closest('div');
    expect(featureCTask).not.toHaveTextContent('local');
  });

  it('renders rejection counter badge when rejection_summaries has items', () => {
    const tasks: Task[] = [
      createTaskWithId('task-1', 'Feature A', { 
        rejection_summaries: ['First rejection'] 
      }),
      createTaskWithId('task-2', 'Feature B', { 
        rejection_summaries: ['First', 'Second', 'Third'] 
      }),
      createTaskWithId('task-3', 'Feature C', { rejection_summaries: [] }),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.getByText('1 rejeição')).toBeInTheDocument();
    expect(screen.getByText('3 rejeições')).toBeInTheDocument();
    expect(screen.getByText('1 rejeição')).toHaveTextContent('1 rejeição');
    expect(screen.getByText('3 rejeições')).toHaveTextContent('3 rejeições');
  });

  it('renders escalating no-progress warnings based on streak length', () => {
    const tasks: Task[] = [
      createMockTask({ no_progress_streak: 1, id: 'task-0' }),
      createMockTask({ no_progress_streak: 2, id: 'task-1' }),
      createMockTask({ no_progress_streak: 3, id: 'task-2' }),
      createMockTask({ no_progress_streak: 5, id: 'task-3' }),
    ];

    render(<TaskList tasks={tasks} />);

    // streak 2 → amber "Sem progresso (n)"; streak ≥ 3 → red "Loop (n ciclos)"
    expect(screen.getByText('Sem progresso (2)')).toBeInTheDocument();
    expect(screen.getByText('Loop (3 ciclos)')).toBeInTheDocument();
    expect(screen.getByText('Loop (5 ciclos)')).toBeInTheDocument();
    expect(screen.queryByText('Sem progresso (1)')).not.toBeInTheDocument();
  });

  it('renders cost chip when cost_usd or max_usd is set', () => {
    const tasks: Task[] = [
      createMockTask({ id: 't-cap', cost_usd: 0.5, max_usd: 1.0 }),
      createMockTask({ id: 't-overrun', cost_usd: 1.5, max_usd: 1.0 }),
      createMockTask({ id: 't-no-cap', cost_usd: 0.42, max_usd: null }),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.getByText('$0.50 / $1.00')).toBeInTheDocument();
    const overrun = screen.getByText('$1.50 / $1.00');
    expect(overrun).toHaveClass('bg-red-50');
    expect(screen.getByText('$0.42')).toBeInTheDocument();
  });

  it('renders fast-track badge when skip_homologation is true', () => {
    const tasks: Task[] = [
      createMockTask({ id: 't-fast', skip_homologation: true }),
      createMockTask({ id: 't-normal', skip_homologation: false }),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.getAllByText('fast-track').length).toBe(1);
  });

  it('does not render indicators when values are zero/false', () => {
    const tasks: Task[] = [
      createMockTask({ 
        tdd: false,
        rejection_summaries: [],
        no_progress_streak: 0,
        id: 'task-1'
      }),
    ];

    render(<TaskList tasks={tasks} />);

    expect(screen.queryByText('claude')).not.toBeInTheDocument();
    expect(screen.queryByText('local')).not.toBeInTheDocument();
    expect(screen.queryByText('rejeição')).not.toBeInTheDocument();
    expect(screen.queryByText('Sem progresso')).not.toBeInTheDocument();
  });

  it('toggles task expansion on click', () => {
    const tasks: Task[] = [createMockTask({ id: 'task-1' })];

    const { container } = render(<TaskList tasks={tasks} />);
    const header = container.querySelector('[class*="cursor-pointer"]');

    expect(header).toBeInTheDocument();
    fireEvent.click(header!);

    const details = container.querySelector('[class*="bg-white"]');
    expect(details).toBeInTheDocument();
    expect(screen.getByText('Tentativas:')).toBeInTheDocument();
  });

  it('shows rejection_summaries in expanded view', () => {
    const tasks: Task[] = [
      createMockTask({ 
        rejection_summaries: ['Rejection reason 1', 'Rejection reason 2'],
        id: 'task-1'
      }),
    ];

    const { container } = render(<TaskList tasks={tasks} />);
    const header = container.querySelector('[class*="cursor-pointer"]');

    fireEvent.click(header!);

    expect(screen.getByText('Rejection reason 1')).toBeInTheDocument();
    expect(screen.getByText('Rejection reason 2')).toBeInTheDocument();
  });

  it('shows subtasks in expanded view', () => {
    const tasks: Task[] = [
      createMockTask({ 
        subtasks: [
          { id: 'sub-1', title: 'Subtask 1', status: 'completed' },
          { id: 'sub-2', title: 'Subtask 2', status: 'pending' },
        ],
        id: 'task-1'
      }),
    ];

    const { container } = render(<TaskList tasks={tasks} />);
    const header = container.querySelector('[class*="cursor-pointer"]');

    fireEvent.click(header!);

    expect(screen.getByText('Subtask 1')).toBeInTheDocument();
    expect(screen.getByText('Subtask 2')).toBeInTheDocument();
  });

  it('displays homologation_result with correct colors based on English values', () => {
    const tasks: Task[] = [
      createMockTask({ homologation_result: 'approved', id: 'task-1' }),
      createMockTask({ homologation_result: 'rejected', id: 'task-2' }),
      createMockTask({ homologation_result: null, id: 'task-3' }),
      createMockTask({ homologation_result: 'pending', id: 'task-4' }),
    ];

    const { container } = render(<TaskList tasks={tasks} />);
    const headers = container.querySelectorAll('[class*="cursor-pointer"]');

    headers.forEach((header, idx) => {
      fireEvent.click(header);
    });

    const approvedText = screen.getByText('Aprovado');
    const rejectedText = screen.getByText('Reprovado');
    const pendingText = screen.getByText('Pendente');

    expect(approvedText).toHaveClass('text-green-600');
    expect(rejectedText).toHaveClass('text-red-600');
    expect(pendingText).toHaveClass('text-gray-600');
  });

  it('displays all task details in expanded view', () => {
    const tasks: Task[] = [
      createMockTask({ 
        attempts: 3,
        homologation_result: 'approved',
        rejection_summaries: ['Test rejection'],
        subtasks: [{ id: 's1', title: 'Sub', status: 'pending' }],
        id: 'task-1'
      }),
    ];

    const { container } = render(<TaskList tasks={tasks} />);
    const header = container.querySelector('[class*="cursor-pointer"]');

    fireEvent.click(header!);

    expect(screen.getByText('Tentativas:')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Homologação:')).toBeInTheDocument();
    expect(screen.getByText('Aprovado')).toBeInTheDocument();
    expect(screen.getByText('Rejeições')).toBeInTheDocument();
    expect(screen.getByText('Test rejection')).toBeInTheDocument();
    expect(screen.getByText('Subtarefas')).toBeInTheDocument();
    expect(screen.getByText('Sub')).toBeInTheDocument();
  });
});

describe('chip de status traduzido', () => {
  it('mostra label PT com enum cru no title', () => {
    const task = createMockTask({ id: 'task-001', title: 'X', status: 'pending' });
    render(<TaskList tasks={[task]} />);
    expect(screen.getByText('pendente')).toBeInTheDocument();
    expect(screen.queryByText('pending')).not.toBeInTheDocument();
  });
});
