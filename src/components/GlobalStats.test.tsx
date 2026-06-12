import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import GlobalStats from './GlobalStats';
import type { GlobalStats as GlobalStatsType } from '@/lib/types';

const stats: GlobalStatsType = {
  daily_claude_code_calls: 4,
  daily_local_llm_calls: 10,
  date: '2026-06-12',
  cost_estimate_usd: 1.5,
  daily_tokens: 1000,
  cost_by_model: {},
  daily_calls_unknown_cost: 0,
  projects_touched_today: ['p'],
  tasks_completed_today: 2,
  approval_first_try_rate: 50, // escala 0-100, como o squire grava
};

describe('GlobalStats', () => {
  it('aprovação 1ª usa a escala 0-100 do arquivo (50 → "50%", não "5000%")', () => {
    render(<GlobalStats stats={stats} />);
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.queryByText('5000%')).not.toBeInTheDocument();
  });
});
