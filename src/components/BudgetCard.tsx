import type { GlobalStats, RateLimitState } from "@/lib/types";

interface BudgetCardProps {
  stats: GlobalStats | null;
  rateLimits: Array<{ project_id: string; rate_limit: RateLimitState }>;
}

function pickActiveBudget(
  rateLimits: BudgetCardProps["rateLimits"]
): { project_id: string; rate_limit: RateLimitState } | null {
  const withCap = rateLimits.filter((r) => r.rate_limit.max_daily_usd > 0);
  if (withCap.length === 0) return null;
  return withCap.reduce((acc, cur) =>
    cur.rate_limit.daily_cost_usd > acc.rate_limit.daily_cost_usd ? cur : acc
  );
}

function formatUsd(n: number): string {
  if (n < 1) return `$${n.toFixed(2)}`;
  if (n < 100) return `$${n.toFixed(2)}`;
  return `$${Math.round(n)}`;
}

export default function BudgetCard({ stats, rateLimits }: BudgetCardProps) {
  const dailyCost = stats?.cost_estimate_usd ?? 0;
  const active = pickActiveBudget(rateLimits);
  const cap = active?.rate_limit.max_daily_usd ?? 0;
  const pct = cap > 0 ? Math.min(100, (dailyCost / cap) * 100) : 0;

  const breakdown = Object.entries(stats?.cost_by_model ?? {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);

  let ringColor = "stroke-emerald-500";
  let badge = "text-emerald-700 bg-emerald-50";
  let badgeLabel = "OK";
  if (pct >= 100) {
    ringColor = "stroke-red-600";
    badge = "text-red-700 bg-red-50";
    badgeLabel = "Estourado";
  } else if (pct >= 75) {
    ringColor = "stroke-amber-500";
    badge = "text-amber-700 bg-amber-50";
    badgeLabel = "Atenção";
  } else if (cap === 0) {
    ringColor = "stroke-gray-300";
    badge = "text-gray-600 bg-gray-100";
    badgeLabel = "Sem cap";
  }

  // SVG ring geometry
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const dash = (Math.max(0, Math.min(100, pct)) / 100) * circumference;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border border-gray-200 dark:border-gray-700">
      <div className="flex items-start gap-4">
        <div className="relative w-24 h-24 flex-shrink-0">
          <svg viewBox="0 0 100 100" className="w-24 h-24 -rotate-90">
            <circle
              cx="50"
              cy="50"
              r={radius}
              className="stroke-gray-200 dark:stroke-gray-700"
              strokeWidth="10"
              fill="none"
            />
            <circle
              cx="50"
              cy="50"
              r={radius}
              className={`${ringColor} transition-all duration-500`}
              strokeWidth="10"
              fill="none"
              strokeDasharray={`${dash} ${circumference}`}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-lg font-bold text-gray-900 dark:text-white leading-none">
              {formatUsd(dailyCost)}
            </span>
            {cap > 0 ? (
              <span className="text-[10px] text-gray-500 mt-1">
                / {formatUsd(cap)}
              </span>
            ) : (
              <span className="text-[10px] text-gray-500 mt-1">sem cap</span>
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">
              Custo do dia
            </h3>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${badge}`}
            >
              {badgeLabel}
            </span>
          </div>

          {breakdown.length > 0 ? (
            <ul className="space-y-1">
              {breakdown.slice(0, 4).map(([model, value]) => {
                const total =
                  breakdown.reduce((acc, [, v]) => acc + v, 0) || 1;
                const sharePct = Math.round((value / total) * 100);
                return (
                  <li
                    key={model}
                    className="flex items-center gap-2 text-[11px] text-gray-600 dark:text-gray-300"
                  >
                    <span className="font-mono truncate flex-1" title={model}>
                      {model}
                    </span>
                    <span className="w-20 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                      <span
                        className="block h-1.5 bg-indigo-500"
                        style={{ width: `${sharePct}%` }}
                      />
                    </span>
                    <span className="w-10 text-right">{formatUsd(value)}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-xs text-gray-500 italic">
              Sem breakdown por modelo ainda.
            </p>
          )}

          {active && (
            <p className="text-[10px] text-gray-400 mt-2">
              Cap visível: <code className="font-mono">{active.project_id}</code>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
