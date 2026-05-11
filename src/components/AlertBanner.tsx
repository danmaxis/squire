'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Alert } from '@/lib/types';

interface AlertBannerProps {
  alerts: Alert[];
}

const STORAGE_KEY = 'dismissed_alerts';

const alertKey = (alert: Alert) =>
  `${alert.project_id}::${alert.task_id ?? ''}::${alert.created_at}`;

async function ackAlert(alert: Alert, dismiss: boolean) {
  const res = await fetch('/api/alerts/ack', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: alert.project_id,
      task_id: alert.task_id,
      created_at: alert.created_at,
      dismiss,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'unknown' }));
    throw new Error(err.error ?? 'request_failed');
  }
}

const AlertBanner: React.FC<AlertBannerProps> = ({ alerts }) => {
  const router = useRouter();
  const [hasMounted, setHasMounted] = useState(false);
  const [dismissedKeys, setDismissedKeys] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setDismissedKeys(new Set(JSON.parse(stored) as string[]));
      }
    } catch {
      // localStorage unavailable
    }
    setHasMounted(true);
  }, []);

  const markDismissedLocally = (key: string) => {
    setDismissedKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(next)));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const handleAck = async (alert: Alert) => {
    const key = alertKey(alert);
    setPending(key);
    setError(null);
    try {
      await ackAlert(alert, false);
      markDismissedLocally(key);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(null);
    }
  };

  const handleDismiss = async (alert: Alert) => {
    const key = alertKey(alert);
    setPending(key);
    setError(null);
    try {
      await ackAlert(alert, true);
      markDismissedLocally(key);
      router.refresh();
    } catch (err) {
      // Fall back to local dismiss so UI doesn't get stuck
      markDismissedLocally(key);
      setError((err as Error).message);
    } finally {
      setPending(null);
    }
  };

  if (!hasMounted) return null;

  const activeAlerts = alerts.filter(
    (alert) => !alert.acknowledged && !dismissedKeys.has(alertKey(alert))
  );

  if (activeAlerts.length === 0) {
    return null;
  }

  const getBannerStyle = (severity: string) => {
    if (severity === 'critical') {
      return {
        backgroundColor: '#ef4444',
        color: '#ffffff',
        borderColor: '#b91c1c',
      };
    }
    return {
      backgroundColor: '#f59e0b',
      color: '#1f2937',
      borderColor: '#d97706',
    };
  };

  const getIcon = () => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-5 w-5 mr-2 flex-shrink-0"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  );

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 overflow-y-auto shadow-md"
      aria-live="polite"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="space-y-3">
          {activeAlerts.map((alert) => {
            const key = alertKey(alert);
            const style = getBannerStyle(alert.severity);
            const isBusy = pending === key;
            return (
              <div
                key={key}
                className="flex items-start p-4 rounded-lg border-l-4 shadow-sm"
                style={{ ...style, borderColor: style.borderColor }}
                role="alert"
              >
                <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>
                <div className="ml-3 flex-1 min-w-0">
                  <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-1">
                    <div className="font-semibold text-sm sm:text-base">
                      {alert.project_id}
                      {alert.task_id ? ` — ${alert.task_id}` : ''}
                    </div>
                    <div className="text-xs opacity-90 whitespace-nowrap mt-1 sm:mt-0">
                      {new Date(alert.created_at).toLocaleString()}
                    </div>
                  </div>
                  <p className="mt-1 text-sm opacity-95">{alert.message}</p>
                </div>
                <div className="ml-3 flex items-center gap-1">
                  <button
                    onClick={() => handleAck(alert)}
                    disabled={isBusy}
                    title="Marcar como reconhecido (persistente)"
                    aria-label="Reconhecer alerta"
                    className="px-2 py-1 rounded text-xs font-medium bg-white/20 hover:bg-white/30 disabled:opacity-50"
                    style={{ color: style.color }}
                  >
                    Ack
                  </button>
                  <button
                    onClick={() => handleDismiss(alert)}
                    disabled={isBusy}
                    aria-label="Descartar alerta"
                    title="Remover alerta do estado do squire"
                    className="p-1 rounded opacity-80 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-white disabled:opacity-50"
                    style={{ color: style.color }}
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-5 w-5"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        {error && (
          <div className="mt-2 text-xs text-white bg-black/60 rounded px-2 py-1 inline-block">
            Erro: {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default AlertBanner;
