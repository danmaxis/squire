import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useAutoRefresh } from './useAutoRefresh';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
}));

describe('useAutoRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('retorna lastRefresh null no estado inicial', () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 5000 }));
    expect(result.current.lastRefresh).toBeNull();
  });

  it('retorna isRefreshing false no estado inicial', () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 5000 }));
    expect(result.current.isRefreshing).toBe(false);
  });

  it('define lastRefresh após o timeout inicial de 500ms', async () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 5000 }));

    expect(result.current.lastRefresh).toBeNull();

    // Avança 500ms (trigger do setTimeout inicial) + 300ms (lógica interna do performRefresh)
    await act(async () => {
      vi.advanceTimersByTime(800);
    });

    expect(result.current.lastRefresh).toBeInstanceOf(Date);
  });

  it('atualiza lastRefresh a cada intervalo', async () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 5000 }));

    // Primeiro refresh (500ms inicial)
    await act(async () => {
      vi.advanceTimersByTime(800);
    });
    const firstRefresh = result.current.lastRefresh;
    expect(firstRefresh).toBeInstanceOf(Date);

    // Segundo refresh (intervalo de 5000ms)
    await act(async () => {
      vi.advanceTimersByTime(5300);
    });
    const secondRefresh = result.current.lastRefresh;
    expect(secondRefresh).toBeInstanceOf(Date);
    expect(secondRefresh!.getTime()).toBeGreaterThanOrEqual(firstRefresh!.getTime());
  });

  it('não faz refresh quando enabled é false', async () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 5000, enabled: false }));

    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    expect(result.current.lastRefresh).toBeNull();
  });

  it('triggerRefresh define lastRefresh imediatamente', async () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 30000 }));

    expect(result.current.lastRefresh).toBeNull();

    await act(async () => {
      result.current.triggerRefresh();
      vi.advanceTimersByTime(300);
    });

    expect(result.current.lastRefresh).toBeInstanceOf(Date);
  });

  it('expõe refreshInterval correto', () => {
    const { result } = renderHook(() => useAutoRefresh({ interval: 15000 }));
    expect(result.current.refreshInterval).toBe(15000);
  });
});
