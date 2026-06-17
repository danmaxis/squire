import { CURSOR_STEP_LABELS } from '@/lib/statusMaps';
import type { Checkpoint, CursorStep } from '@/lib/types';
import { RateLimitGauge } from './RateLimitGauge';

interface CheckpointPanelProps {
  checkpoint: Checkpoint | null;
}

const stepColors: Record<CursorStep, string> = {
  planning: 'bg-gray-100 text-gray-700',
  red_phase: 'bg-red-100 text-red-700',
  llm_execution: 'bg-blue-100 text-blue-700',
  testing: 'bg-cyan-100 text-cyan-700',
  homologation: 'bg-purple-100 text-purple-700',
  completed: 'bg-green-100 text-green-700',
};

const phaseColors: Record<string, string> = {
  planning: 'bg-gray-100 text-gray-700',
  implementing: 'bg-blue-100 text-blue-700',
  reviewing: 'bg-purple-100 text-purple-700',
  blocked: 'bg-red-100 text-red-700',
  completed: 'bg-green-100 text-green-700',
};

function truncateLines(text: string, maxChars: number, maxLines: number): string {
  const truncated = text.length > maxChars ? text.slice(0, maxChars) + '...' : text;
  const lines = truncated.split('\n');
  if (lines.length > maxLines) {
    return lines.slice(0, maxLines).join('\n') + '...';
  }
  return truncated;
}

function calculateUptime(startedAt: string, lastHeartbeat: string): string {
  const start = new Date(startedAt).getTime();
  const end = new Date(lastHeartbeat).getTime();
  const diffMinutes = Math.floor((end - start) / (1000 * 60));
  return `Ativo há ${diffMinutes}min`;
}

export function CheckpointPanel({ checkpoint }: CheckpointPanelProps) {
  if (!checkpoint) {
    return null;
  }

  const { cursor, llm_context, phase, session_id, started_at, last_heartbeat, recovery, rate_limit } = checkpoint;

  const currentTaskId = cursor.current_task_id ?? 'Nenhuma';
  const stepColor = stepColors[cursor.step] || 'bg-gray-100 text-gray-700';
  const phaseColor = phaseColors[phase] || 'bg-gray-100 text-gray-700';

  const instructionPreview = truncateLines(llm_context.last_instruction, 150, 2);
  const testFraction = `${llm_context.tests_passing} passando / ${llm_context.tests_failing} falhando`;
  const testColor = llm_context.tests_failing === 0 ? 'text-green-600' : 'text-red-600';
  const filesToShow = llm_context.files_touched.slice(0, 5);
  const filesMore = llm_context.files_touched.length > 5 ? `+${llm_context.files_touched.length - 5} mais` : null;

  const showRecovery = recovery.escalation_needed || !recovery.can_resume;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      <h2 className="text-sm font-semibold text-gray-700 mb-2">Checkpoint</h2>

      {/* CURSOR SECTION */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600">Tarefa:</span>
          <span className="text-sm font-medium text-gray-900">{currentTaskId}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-1 rounded text-xs font-medium ${stepColor}`}
            title={cursor.step}
          >
            {CURSOR_STEP_LABELS[cursor.step] ?? cursor.step}
          </span>
          <span className="text-xs text-gray-600">
            Tentativa #{cursor.attempt}
          </span>
          <span className="text-xs text-gray-600">
              Homologação #{cursor.homologation_attempt}
            </span>
        </div>
      </div>

      {/* LLM CONTEXT SECTION */}
      <div className="space-y-2">
        <div className="text-xs text-gray-600">
          <span className="font-medium">Última instrução:</span>
          <p className="text-gray-800 mt-1">{instructionPreview}</p>
        </div>
        <div className="flex flex-wrap gap-1">
          {filesToShow.map((file, idx) => (
            <span key={idx} className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-700">
              {file}
            </span>
          ))}
          {filesMore && (
            <span className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-700">
              {filesMore}
            </span>
          )}
        </div>
        <div className={`text-sm font-medium ${testColor}`}>
          {testFraction}
        </div>
      </div>

      {/* SESSION SECTION */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-1 rounded text-xs font-medium ${phaseColor}`}>
            {phase}
          </span>
          <span className="text-xs text-gray-600 font-mono">{session_id}</span>
        </div>
        <div className="text-xs text-gray-600">
          {calculateUptime(started_at, last_heartbeat)}
        </div>
        <div className="pt-2">
          <RateLimitGauge rate_limit={rate_limit ?? null} />
        </div>
      </div>

      {/* RECOVERY SECTION */}
      {showRecovery && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <div className="flex items-start gap-2">
            <svg
              className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div className="flex-1">
              {recovery.escalation_needed && (
                <div className="text-sm font-medium text-amber-800 mb-1">
                  Escalação necessária
                </div>
              )}
              {recovery.blocked_reason && (
                <div className="text-sm text-amber-700 mb-1">
                  Bloqueado: {recovery.blocked_reason}
                </div>
              )}
              {recovery.resume_action && (
                <div className="text-sm text-amber-700">
                  Ação: {recovery.resume_action}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
