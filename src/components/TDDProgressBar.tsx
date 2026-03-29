import type { Task, Cursor, LLMContextSummary, CursorStep } from '@/lib/types';

interface TDDProgressBarProps {
  task: Task;
  cursor: Cursor;
  llm_context: LLMContextSummary;
}

const STEP_LABELS: Record<CursorStep, string> = {
  planning: 'Planejamento',
  red_phase: 'RED (testes)',
  llm_execution: 'Implementação',
  testing: 'Rodando testes',
  homologation: 'Homologação',
  completed: 'Concluído',
};

const STEP_ORDER: CursorStep[] = ['planning', 'red_phase', 'llm_execution', 'testing', 'homologation', 'completed'];

const getStepColor = (step: CursorStep, isCompleted: boolean, isCurrent: boolean): string => {
  if (isCompleted) {
    return step === 'completed' ? 'bg-green-600 border-green-600' : 'bg-blue-600 border-blue-600';
  }
  if (isCurrent) {
    return step === 'completed' ? 'bg-green-500 border-green-500' : 'bg-blue-500 border-blue-500';
  }
  return 'bg-white border-gray-400';
};

const getLabelColor = (isCompleted: boolean, isCurrent: boolean): string => {
  if (isCompleted) return 'text-gray-900 font-semibold';
  if (isCurrent) return 'text-gray-900 font-bold';
  return 'text-gray-500';
};

export function TDDProgressBar({ task, cursor, llm_context }: TDDProgressBarProps) {
  if (!task.tdd || cursor.current_task_id !== task.id) {
    return null;
  }

  const currentStepIndex = STEP_ORDER.indexOf(cursor.step);

  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        {STEP_ORDER.map((step, index) => {
          const isCompleted = index < currentStepIndex;
          const isCurrent = index === currentStepIndex;
          const stepColor = getStepColor(step, isCompleted, isCurrent);
          const labelColor = getLabelColor(isCompleted, isCurrent);

          let extraInfo: string | null = null;

          if (isCurrent) {
            if (step === 'red_phase') {
              extraInfo = `${task.test_author === 'claude' ? 'Claude' : 'Local LLM'}`;
            } else if (step === 'llm_execution') {
              extraInfo = `Tentativa ${cursor.attempt}/${task.max_attempts}`;
            } else if (step === 'testing') {
              extraInfo = `${llm_context.tests_passing} passando, ${llm_context.tests_failing} falhando`;
            } else if (step === 'homologation') {
              extraInfo = `Homologação ${cursor.homologation_attempt}/${task.max_homologation_attempts}`;
            }
          }

          return (
            <div key={step} className="flex flex-col items-center flex-1">
              <div
                className={`w-10 h-10 rounded-full border-2 flex items-center justify-center ${stepColor} ${
                  isCurrent ? 'ring-4 ring-blue-200' : ''
                }`}
              >
                {isCompleted ? (
                  <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <div className="w-3 h-3 rounded-full bg-current" />
                )}
              </div>
              <span className={`text-xs mt-2 text-center ${labelColor}`}>
                {STEP_LABELS[step]}
              </span>
              {extraInfo && (
                <span className="text-xs mt-1 text-center text-gray-600">{extraInfo}</span>
              )}
            </div>
          );
        })}
      </div>
      <div className="relative w-full mt-4">
        <div className="absolute top-1/2 left-0 w-full h-0.5 bg-gray-300 -translate-y-1/2" />
        <div
          className="absolute top-1/2 left-0 h-0.5 bg-blue-500 -translate-y-1/2 transition-all duration-300"
          style={{ width: `${(currentStepIndex / (STEP_ORDER.length - 1)) * 100}%` }}
        />
      </div>
    </div>
  );
}
