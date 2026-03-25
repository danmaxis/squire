'use client';

import React from 'react';

interface RefreshIndicatorProps {
  lastRefresh: Date | null;
  isRefreshing: boolean;
  refreshInterval: number;
  /** Opcional: indica falha detectada externamente */
  isError?: boolean;
}

/**
 * Indicador visual de status do auto-refresh.
 * Exibe um dot pulsante (verde=ok, amarelo=atualizando, vermelho=erro) e o timestamp.
 */
export function RefreshIndicator({
  lastRefresh,
  isRefreshing,
  refreshInterval,
  isError = false,
}: RefreshIndicatorProps) {
  const formatTime = (date: Date | null) => {
    if (!date) return '--:--:--';
    return date.toLocaleTimeString('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const statusColor = isError
    ? 'bg-red-500'
    : isRefreshing
    ? 'bg-yellow-400'
    : 'bg-green-500';
  const statusText = isError ? 'Erro' : isRefreshing ? 'Atualizando...' : 'Atualizado';

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 dark:bg-gray-800 rounded-full border border-gray-200 dark:border-gray-700 shadow-sm text-xs font-medium text-gray-600 dark:text-gray-300">
      {/* Dot pulsante */}
      <div className="relative flex h-2.5 w-2.5">
        <span
          className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${statusColor}`}
        />
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${statusColor}`} />
      </div>

      <span className={`hidden sm:inline ${isError ? 'text-red-600 dark:text-red-400' : ''}`}>
        {statusText}
      </span>

      <span className="font-mono text-[10px] opacity-75">{formatTime(lastRefresh)}</span>

      <span className="text-[10px] opacity-50">({Math.round(refreshInterval / 1000)}s)</span>
    </div>
  );
}
