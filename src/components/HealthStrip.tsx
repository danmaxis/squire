import Link from 'next/link';
import { readSessionLock } from '@/lib/squireLock';
import { getAlerts, getGlobalStats, getProjects, getCheckpoint } from '@/lib/data';
import type { RateLimitState } from '@/lib/types';

async function gatherBudget(): Promise<{
  spent: number;
  cap: number;
  pct: number;
} | null> {
  const projects = await getProjects();
  if (projects.length === 0) return null;

  const rateLimits: RateLimitState[] = [];
  for (const p of projects) {
    const cp = await getCheckpoint(p.id);
    if (cp?.rate_limit) rateLimits.push(cp.rate_limit);
  }

  const stats = await getGlobalStats();
  const spent = stats?.cost_estimate_usd ?? 0;
  const withCap = rateLimits.filter((r) => r.max_daily_usd > 0);
  const cap = withCap.length === 0 ? 0 : Math.max(...withCap.map((r) => r.max_daily_usd));
  const pct = cap > 0 ? Math.min(100, (spent / cap) * 100) : 0;
  return { spent, cap, pct };
}

export default async function HealthStrip() {
  const lock = await readSessionLock();
  const alerts = await getAlerts();
  const activeAlerts = alerts.filter((a) => !a.acknowledged).length;
  const budget = await gatherBudget();

  const status = lock.held
    ? { dot: 'bg-green-500', label: 'Squire ativo', detail: lock.holder ?? '?' }
    : lock.acquiredAt
    ? { dot: 'bg-gray-400', label: 'Squire ocioso', detail: 'lock expirado' }
    : { dot: 'bg-gray-300', label: 'Sem sessão', detail: 'sem lock' };

  let budgetClass = 'text-gray-600';
  let budgetLabel = budget && budget.cap > 0
    ? `$${budget.spent.toFixed(2)} / $${budget.cap.toFixed(2)}`
    : budget
    ? `$${budget.spent.toFixed(2)}`
    : '—';
  if (budget && budget.cap > 0) {
    if (budget.pct >= 100) budgetClass = 'text-red-700 font-semibold';
    else if (budget.pct >= 75) budgetClass = 'text-amber-700 font-semibold';
    else budgetClass = 'text-emerald-700';
  }

  return (
    <div
      aria-live="polite"
      className="sticky top-0 z-20 bg-white/80 backdrop-blur border-b border-gray-200 dark:bg-gray-900/80 dark:border-gray-700"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-9 flex items-center justify-between text-xs">
        <Link href="/" className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${status.dot}`} />
          <span className="font-medium text-gray-700 dark:text-gray-200">
            {status.label}
          </span>
          <span className="text-gray-400 font-mono truncate max-w-[160px]">
            {status.detail}
          </span>
        </Link>

        <div className="flex items-center gap-4">
          <span className={`font-mono ${budgetClass}`} title="Custo hoje / cap diário">
            💰 {budgetLabel}
          </span>

          {activeAlerts > 0 ? (
            <Link
              href="/"
              className="text-amber-700 dark:text-amber-300 font-semibold"
              title={`${activeAlerts} alertas não reconhecidos`}
            >
              ⚠ {activeAlerts}
            </Link>
          ) : (
            <span className="text-gray-400" title="Sem alertas ativos">
              ⚠ 0
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
