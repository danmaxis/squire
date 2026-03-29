import { render, screen } from '@testing-library/react';
import { RateLimitGauge } from './RateLimitGauge';
import type { RateLimitState } from '@/lib/types';

describe('RateLimitGauge', () => {
  const fixedNow = 1000000000000; // 2001-09-09T01:46:40.000Z

  const createRateLimitState = (overrides?: Partial<RateLimitState>): RateLimitState => ({
    claude_code_calls_this_window: 5,
    window_started_at: new Date(fixedNow - 5 * 60000).toISOString(), // 5 min ago
    window_duration_minutes: 10,
    max_calls_per_window: 10,
    ...overrides,
  });

  beforeEach(() => {
    vi.spyOn(Date, 'now').mockReturnValue(fixedNow);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('rate_limit null renderiza "Limite: sem dados"', () => {
    render(<RateLimitGauge rate_limit={null} />);
    expect(screen.getByText('Limite: sem dados')).toBeInTheDocument();
  });

  test('usage 0-50% aplica bg-green-500 e mostra texto correto', () => {
    const rateLimit: RateLimitState = {
      claude_code_calls_this_window: 3,
      window_started_at: new Date(fixedNow - 5 * 60000).toISOString(),
      window_duration_minutes: 10,
      max_calls_per_window: 10,
    };

    render(<RateLimitGauge rate_limit={rateLimit} />);

    expect(screen.getByText('3 / 10 chamadas Claude Code')).toBeInTheDocument();
    const progressbar = screen.getByRole('progressbar');
    const innerDiv = progressbar.querySelector('div');
    expect(innerDiv).toHaveClass('bg-green-500');
  });

  test('usage >80% aplica bg-red-500', () => {
    const rateLimit: RateLimitState = {
      claude_code_calls_this_window: 9,
      window_started_at: new Date(fixedNow - 5 * 60000).toISOString(),
      window_duration_minutes: 10,
      max_calls_per_window: 10,
    };

    render(<RateLimitGauge rate_limit={rateLimit} />);

    const progressbar = screen.getByRole('progressbar');
    const innerDiv = progressbar.querySelector('div');
    expect(innerDiv).toHaveClass('bg-red-500');
  });

  test('usage 51-80% aplica bg-yellow-500', () => {
    const rateLimit: RateLimitState = {
      claude_code_calls_this_window: 6,
      window_started_at: new Date(fixedNow - 5 * 60000).toISOString(),
      window_duration_minutes: 10,
      max_calls_per_window: 10,
    };

    render(<RateLimitGauge rate_limit={rateLimit} />);

    const progressbar = screen.getByRole('progressbar');
    const innerDiv = progressbar.querySelector('div');
    expect(innerDiv).toHaveClass('bg-yellow-500');
  });

  test('exibe "Janela reseta em Xmin" quando janela ativa', () => {
    const rateLimit: RateLimitState = {
      claude_code_calls_this_window: 3,
      window_started_at: new Date(fixedNow - 5 * 60000).toISOString(),
      window_duration_minutes: 10,
      max_calls_per_window: 10,
    };

    render(<RateLimitGauge rate_limit={rateLimit} />);

    expect(screen.getByText('Janela reseta em 5min')).toBeInTheDocument();
  });

  test('exibe "Janela resetada" quando janela expirada', () => {
    const rateLimit: RateLimitState = {
      claude_code_calls_this_window: 3,
      window_started_at: new Date(fixedNow - 15 * 60000).toISOString(), // 15 min ago
      window_duration_minutes: 10,
      max_calls_per_window: 10,
    };

    render(<RateLimitGauge rate_limit={rateLimit} />);

    expect(screen.getByText('Janela resetada')).toBeInTheDocument();
  });
});
