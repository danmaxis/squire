'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';

const DEFAULT_REFRESH_INTERVAL = parseInt(
  process.env.NEXT_PUBLIC_REFRESH_INTERVAL || '30000',
  10
);

interface UseAutoRefreshOptions {
  /** Intervalo em ms. Default: NEXT_PUBLIC_REFRESH_INTERVAL ou 30000 */
  interval?: number;
  /** Se false, não inicia o polling automaticamente */
  enabled?: boolean;
}

interface UseAutoRefreshReturn {
  lastRefresh: Date | null;
  isRefreshing: boolean;
  refreshInterval: number;
  /** Dispara um refresh manual imediato */
  triggerRefresh: () => void;
}

/**
 * Hook para auto-refresh de dados via polling usando router.refresh() do Next.js App Router.
 *
 * Notas:
 * - router.refresh() é síncrono (void) — não lança exceções capturáveis.
 *   O status isRefreshing é gerenciado localmente via setTimeout de curta duração.
 * - useState garante re-renders quando lastRefresh/isRefreshing mudam.
 * - timerRef evita que o clearInterval seja afetado por re-renders.
 */
export function useAutoRefresh(options: UseAutoRefreshOptions = {}): UseAutoRefreshReturn {
  const { interval = DEFAULT_REFRESH_INTERVAL, enabled = true } = options;

  const router = useRouter();

  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Ref para evitar closure stale no callback do setInterval
  const isRefreshingRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const performRefresh = useCallback(() => {
    if (isRefreshingRef.current) return;

    isRefreshingRef.current = true;
    setIsRefreshing(true);

    // Instrui o Next.js a revalidar os dados do servidor sem recarregar a página.
    // É síncrono (void) — não retorna Promise e não lança exceções.
    router.refresh();

    // Aguarda um tick para o React processar e então atualiza o estado
    setTimeout(() => {
      isRefreshingRef.current = false;
      setIsRefreshing(false);
      setLastRefresh(new Date());
    }, 300);
  }, [router]);

  const triggerRefresh = useCallback(() => {
    performRefresh();
  }, [performRefresh]);

  useEffect(() => {
    if (!enabled) return;

    // Dispara o primeiro refresh logo após a hidratação, sem esperar o intervalo completo
    const initialTimer = setTimeout(performRefresh, 500);
    timerRef.current = setInterval(performRefresh, interval);

    return () => {
      clearTimeout(initialTimer);
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
    // performRefresh é estável enquanto router não mudar
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interval, enabled]);

  return {
    lastRefresh,
    isRefreshing,
    refreshInterval: interval,
    triggerRefresh,
  };
}
