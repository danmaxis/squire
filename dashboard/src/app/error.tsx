'use client';

import { AlertTriangle } from 'lucide-react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="max-w-md space-y-4 rounded-lg border border-red-200 bg-red-50 p-6 text-center dark:border-red-800 dark:bg-red-950">
        <AlertTriangle className="mx-auto h-8 w-8 text-red-500" />
        <h2 className="text-lg font-semibold text-red-800 dark:text-red-200">
          Algo quebrou ao renderizar esta página
        </h2>
        <p className="text-sm text-red-700 dark:text-red-300">
          {error.message || 'Erro inesperado.'}
          {error.digest && (
            <span className="mt-1 block font-mono text-xs text-red-400">
              digest: {error.digest}
            </span>
          )}
        </p>
        <p className="text-xs text-red-600 dark:text-red-400">
          Geralmente é um JSON de estado inválido — verifique os arquivos do
          projeto em squire-state ou rode `squire doctor`.
        </p>
        <button
          onClick={reset}
          className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
        >
          Tentar de novo
        </button>
      </div>
    </div>
  );
}
