import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useCommandPoll } from './useCommandPoll';

const UUID = '12345678-1234-1234-1234-123456789abc';

function statusResponse(status: string, result: unknown = null) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ status, command: null, result }),
  };
}

describe('useCommandPoll', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('idle sem commandId', () => {
    const { result } = renderHook(() => useCommandPoll(null));
    expect(result.current.phase).toBe('idle');
  });

  it('vai a done quando o comando completa', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      statusResponse('done', { status: 'done', exit_code: 0 })
    );
    const { result } = renderHook(() => useCommandPoll(UUID));
    await waitFor(() => expect(result.current.phase).toBe('done'));
    expect(result.current.result?.exit_code).toBe(0);
  });

  it('tolera falhas transitórias de rede antes de desistir', async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('net down'))
      .mockRejectedValueOnce(new Error('net down'))
      .mockResolvedValueOnce(statusResponse('done', { status: 'done', exit_code: 0 }));

    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useCommandPoll(UUID));
      // 1ª falha + 2ª falha + sucesso (2s entre cada)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
        await vi.advanceTimersByTimeAsync(2100);
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(result.current.phase).toBe('done');
    } finally {
      vi.useRealTimers();
    }
  });

  it('desiste após exceder as falhas toleradas', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('net down'));
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useCommandPoll(UUID));
      await act(async () => {
        for (let i = 0; i < 5; i++) {
          await vi.advanceTimersByTimeAsync(2100);
        }
      });
      expect(result.current.phase).toBe('error');
      expect(result.current.error).toBe('net down');
    } finally {
      vi.useRealTimers();
    }
  });

  it('404 não é erro — continua tentando', async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({}) })
      .mockResolvedValueOnce(statusResponse('running'))
      .mockResolvedValueOnce(statusResponse('done', { status: 'done', exit_code: 0 }));
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useCommandPoll(UUID));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(result.current.phase).toBe('running');
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(result.current.phase).toBe('done');
    } finally {
      vi.useRealTimers();
    }
  });
});
