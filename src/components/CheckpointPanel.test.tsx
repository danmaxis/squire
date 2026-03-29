import { render, screen } from '@testing-library/react';
import { CheckpointPanel } from './CheckpointPanel';
import type { Checkpoint } from '@/lib/types';

const createCheckpoint = (overrides?: Partial<Checkpoint>): Checkpoint => ({
  version: 1,
  session_id: 'sess-abc123',
  phase: 'implementing',
  started_at: '2026-03-29T10:00:00Z',
  last_heartbeat: '2026-03-29T10:30:00Z',
  cursor: {
    current_task_id: 'task-456',
    current_subtask_id: 'sub-789',
    step: 'llm_execution',
    attempt: 2,
    homologation_attempt: 1,
    ...overrides?.cursor,
  },
  llm_context: {
    last_instruction:
      'Implementar função de validação de email com regex e testar casos edge case',
    files_touched: ['src/utils/email.ts', 'src/types/auth.ts', 'src/validation.ts'],
    last_error: null,
    tests_passing: 5,
    tests_failing: 0,
    test_summary: 'Todos os testes passaram',
    ...overrides?.llm_context,
  },
  rate_limit: {
    claude_code_calls_this_window: 10,
    window_started_at: '2026-03-29T10:00:00Z',
    window_duration_minutes: 60,
    max_calls_per_window: 100,
  },
  recovery: {
    can_resume: true,
    resume_action: 'Continuar execução normal',
    blocked_reason: null,
    escalation_needed: false,
    ...overrides?.recovery,
  },
  ...overrides,
});

describe('CheckpointPanel', () => {
  it('retorna null quando checkpoint=null', () => {
    const { container } = render(<CheckpointPanel checkpoint={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('renderiza task ID e step badge corretamente', () => {
    const checkpoint = createCheckpoint({
      cursor: {
        current_task_id: 'task-xyz',
        current_subtask_id: null,
        step: 'red_phase',
        attempt: 3,
        homologation_attempt: 2,
      },
    });

    render(<CheckpointPanel checkpoint={checkpoint} />);

    expect(screen.getByText('Tarefa:')).toBeInTheDocument();
    expect(screen.getByText('task-xyz')).toBeInTheDocument();
    expect(screen.getByText('red_phase')).toBeInTheDocument();
    expect(screen.getByText('Tentativa #3')).toBeInTheDocument();
    expect(screen.getByText('Homologação #2')).toBeInTheDocument();
  });

  it('exibe Nenhuma quando current_task_id é null', () => {
    const checkpoint = createCheckpoint({
      cursor: {
        current_task_id: null,
        current_subtask_id: null,
        step: 'planning',
        attempt: 1,
        homologation_attempt: 0,
      },
    });

    render(<CheckpointPanel checkpoint={checkpoint} />);
    expect(screen.getByText('Nenhuma')).toBeInTheDocument();
  });

  it('mostra seção de recovery quando escalation_needed=true ou can_resume=false', () => {
    const checkpointWithEscalation = createCheckpoint({
      recovery: {
        can_resume: true,
        resume_action: 'Reiniciar sessão',
        blocked_reason: 'Timeout na execução',
        escalation_needed: true,
      },
    });

    render(<CheckpointPanel checkpoint={checkpointWithEscalation} />);
    expect(screen.getByText('Escalação necessária')).toBeInTheDocument();
    expect(screen.getByText('Bloqueado: Timeout na execução')).toBeInTheDocument();

    const checkpointNoResume = createCheckpoint({
      recovery: {
        can_resume: false,
        resume_action: 'Reiniciar sessão',
        blocked_reason: 'Dependência não resolvida',
        escalation_needed: false,
      },
    });

    render(<CheckpointPanel checkpoint={checkpointNoResume} />);
    expect(screen.getByText('Bloqueado: Dependência não resolvida')).toBeInTheDocument();
  });

  it('oculta seção de recovery quando ambos ok (escalation_needed=false e can_resume=true)', () => {
    const checkpoint = createCheckpoint({
      recovery: {
        can_resume: true,
        resume_action: 'Continuar',
        blocked_reason: null,
        escalation_needed: false,
      },
    });

    render(<CheckpointPanel checkpoint={checkpoint} />);
    expect(screen.queryByText('Escalação necessária')).not.toBeInTheDocument();
    expect(screen.queryByText('Bloqueado:')).not.toBeInTheDocument();
  });

  it('trunca last_instruction em 150 chars e 2 linhas', () => {
    const longInstruction =
      'Esta é uma instrução muito longa que excede 150 caracteres e deve ser truncada corretamente pelo componente CheckpointPanel para não quebrar o layout da interface do usuário';
    const checkpoint = createCheckpoint({
      llm_context: {
        last_instruction: longInstruction,
        files_touched: [],
        last_error: null,
        tests_passing: 0,
        tests_failing: 0,
        test_summary: '',
      },
    });

    render(<CheckpointPanel checkpoint={checkpoint} />);
    const instructionText = screen.getByText(/Última instrução:/).nextElementSibling;
    expect(instructionText?.textContent).toMatch(/...$/);
    expect(instructionText?.textContent?.split('\n').length).toBeLessThanOrEqual(3);
  });
});
