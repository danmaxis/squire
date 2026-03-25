'use client';

import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import { RefreshIndicator } from './RefreshIndicator';

/**
 * Client component que ativa o polling de auto-refresh e exibe o indicador visual.
 * Deve ser montado uma única vez no layout ou página principal.
 * O router.refresh() disparado aqui faz o Next.js revalidar todos os server components ativos.
 */
export function RefreshController() {
  const { lastRefresh, isRefreshing, refreshInterval } = useAutoRefresh();

  return (
    <RefreshIndicator
      lastRefresh={lastRefresh}
      isRefreshing={isRefreshing}
      refreshInterval={refreshInterval}
    />
  );
}
