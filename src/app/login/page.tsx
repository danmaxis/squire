'use client';

import React, { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { KeyRound } from 'lucide-react';
import { setWriteToken } from '@/lib/clientApi';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token, setToken] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setChecking(true);
    try {
      const res = await fetch('/api/auth/check', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 204) {
        setWriteToken(token);
        router.push(searchParams.get('from') ?? '/');
        return;
      }
      if (res.status === 503) {
        setError('Escrita desabilitada no servidor (DASHBOARD_WRITE_TOKEN não configurado).');
      } else {
        setError('Token inválido.');
      }
    } catch {
      setError('Falha ao validar o token.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-zinc-700 bg-zinc-900 p-6"
      >
        <div className="flex items-center gap-2 text-zinc-100">
          <KeyRound className="h-5 w-5" />
          <h1 className="text-lg font-semibold">Acesso de escrita</h1>
        </div>
        <p className="text-sm text-zinc-400">
          Informe o token de escrita do dashboard para criar projetos, editar
          tasks e controlar execuções.
        </p>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Token"
          autoFocus
          className="w-full rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-cyan-500 focus:outline-none"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={checking || !token}
          className="w-full rounded bg-cyan-600 px-3 py-2 text-sm font-medium text-white hover:bg-cyan-500 disabled:opacity-50"
        >
          {checking ? 'Validando…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
