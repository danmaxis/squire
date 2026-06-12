'use client';

import Link from 'next/link';
import { AlertTriangle } from 'lucide-react';

export default function ProjectError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-4 p-8">
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-950">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <h2 className="text-lg font-semibold text-red-800 dark:text-red-200">
            Falha ao renderizar este projeto
          </h2>
        </div>
        <p className="mt-2 text-sm text-red-700 dark:text-red-300">
          {error.message || 'Erro inesperado.'}
        </p>
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">
          Causa comum: arquivo de estado malformado (tasks.json,
          checkpoint.json…) — confira o diretório do projeto em squire-state.
        </p>
        <div className="mt-4 flex gap-2">
          <button
            onClick={reset}
            className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
          >
            Tentar de novo
          </button>
          <Link
            href="/"
            className="rounded border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100 dark:text-red-300"
          >
            ← Todos os projetos
          </Link>
        </div>
      </div>
    </div>
  );
}
