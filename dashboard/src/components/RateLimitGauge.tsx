import type { RateLimitState } from '@/lib/types';

interface RateLimitGaugeProps {
  rate_limit: RateLimitState | null;
}

export function RateLimitGauge({ rate_limit }: RateLimitGaugeProps) {
  if (!rate_limit) {
    return (
      <div className="text-xs text-gray-500">
        Limite: sem dados
      </div>
    );
  }

  const {
    claude_code_calls_this_window,
    window_started_at,
    window_duration_minutes,
    max_calls_per_window,
  } = rate_limit;

  const usagePercentage = max_calls_per_window > 0
    ? (claude_code_calls_this_window / max_calls_per_window) * 100
    : 0;

  let bgColor = 'bg-green-500';
  if (usagePercentage > 80) {
    bgColor = 'bg-red-500';
  } else if (usagePercentage > 50) {
    bgColor = 'bg-yellow-500';
  }

  const windowEnd = new Date(window_started_at).getTime() + window_duration_minutes * 60000;
  const minutesLeft = Math.max(0, Math.ceil((windowEnd - Date.now()) / 60000));

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs font-medium text-gray-700">
          {claude_code_calls_this_window} / {max_calls_per_window} chamadas Claude Code
        </span>
        <span className="text-xs text-gray-500">
          {minutesLeft === 0
            ? 'Janela resetada'
            : `Janela reseta em ${minutesLeft}min`}
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2" role="progressbar" aria-valuenow={claude_code_calls_this_window} aria-valuemin={0} aria-valuemax={max_calls_per_window}>
        <div
          className={`${bgColor} h-2 rounded-full transition-all duration-300`}
          style={{ width: `${Math.min(100, usagePercentage)}%` }}
        />
      </div>
    </div>
  );
}
