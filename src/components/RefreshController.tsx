'use client';

import { useAutoRefresh } from '@/hooks/useAutoRefresh';
import { RefreshIndicator } from './RefreshIndicator';

const HOT_VIEW_INTERVAL_MS = 5000;
const IDLE_INTERVAL_MS = parseInt(
  process.env.NEXT_PUBLIC_REFRESH_INTERVAL || '30000',
  10
);

interface RefreshControllerProps {
  /** True when squire is actively running this page's subject (phase=implementing).
   * Triggers a faster 5s poll cadence so transitions feel live. */
  hot?: boolean;
}

export function RefreshController({ hot = false }: RefreshControllerProps) {
  const interval = hot ? HOT_VIEW_INTERVAL_MS : IDLE_INTERVAL_MS;
  const { lastRefresh, isRefreshing, refreshInterval } = useAutoRefresh({
    interval,
  });

  return (
    <RefreshIndicator
      lastRefresh={lastRefresh}
      isRefreshing={isRefreshing}
      refreshInterval={refreshInterval}
      mode={hot ? 'live' : 'idle'}
    />
  );
}
