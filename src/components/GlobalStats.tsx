import type { GlobalStats } from '@/lib/types';

interface GlobalStatsProps {
  stats: GlobalStats | null;
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

interface TileProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  iconBg: string;
  iconText: string;
  icon: React.ReactNode;
}

function Tile({ label, value, hint, iconBg, iconText, icon }: TileProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 flex items-center space-x-3 border border-gray-200 dark:border-gray-700">
      <div className={`p-2.5 ${iconBg} rounded-full ${iconText}`}>{icon}</div>
      <div className="min-w-0">
        <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">
          {label}
        </p>
        <p className="text-xl font-bold text-gray-900 dark:text-white">{value}</p>
        {hint && (
          <p className="text-[10px] text-gray-500 dark:text-gray-400">{hint}</p>
        )}
      </div>
    </div>
  );
}

export default function GlobalStats({ stats }: GlobalStatsProps) {
  const localCalls = stats?.daily_local_llm_calls ?? 0;
  const claudeCalls = stats?.daily_claude_code_calls ?? 0;
  const totalCalls = localCalls + claudeCalls;
  const localPct = totalCalls > 0 ? Math.round((localCalls / totalCalls) * 100) : 0;
  const claudePct = totalCalls > 0 ? Math.round((claudeCalls / totalCalls) * 100) : 0;
  const tokens = stats?.daily_tokens ?? 0;
  const unknownCalls = stats?.daily_calls_unknown_cost ?? 0;
  const projectsTouched = Array.isArray(stats?.projects_touched_today)
    ? stats!.projects_touched_today.length
    : 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
      <Tile
        label="Projetos Tocados"
        value={projectsTouched}
        iconBg="bg-blue-100 dark:bg-blue-900"
        iconText="text-blue-600 dark:text-blue-300"
        icon={
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        }
      />

      <Tile
        label="Tasks Hoje"
        value={stats?.tasks_completed_today ?? 0}
        iconBg="bg-green-100 dark:bg-green-900"
        iconText="text-green-600 dark:text-green-300"
        icon={
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      />

      <Tile
        label="Chamadas LLM"
        value={totalCalls}
        hint={`${localPct}% local / ${claudePct}% CC`}
        iconBg="bg-purple-100 dark:bg-purple-900"
        iconText="text-purple-600 dark:text-purple-300"
        icon={
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        }
      />

      <Tile
        label="Aprovação 1ª"
        value={
          stats?.approval_first_try_rate !== undefined
            ? // o squire grava em escala 0-100 (ex: 50.0 = 50%) — sem multiplicar
              `${Math.round(stats.approval_first_try_rate)}%`
            : '—'
        }
        iconBg="bg-yellow-100 dark:bg-yellow-900"
        iconText="text-yellow-600 dark:text-yellow-300"
        icon={
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
          </svg>
        }
      />

      <Tile
        label="Tokens Hoje"
        value={formatTokens(tokens)}
        iconBg="bg-indigo-100 dark:bg-indigo-900"
        iconText="text-indigo-600 dark:text-indigo-300"
        icon={
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h10M4 18h6" />
          </svg>
        }
      />

      <Tile
        label="Calls sem custo"
        value={unknownCalls}
        hint={
          unknownCalls > 0
            ? 'custo real provavelmente maior'
            : 'todos os backends reportaram usage'
        }
        iconBg={unknownCalls > 0 ? 'bg-amber-100 dark:bg-amber-900' : 'bg-gray-100 dark:bg-gray-700'}
        iconText={unknownCalls > 0 ? 'text-amber-700 dark:text-amber-300' : 'text-gray-500 dark:text-gray-400'}
        icon={
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      />
    </div>
  );
}
