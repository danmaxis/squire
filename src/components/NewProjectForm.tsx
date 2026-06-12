'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authedFetch } from '@/lib/clientApi';
import { useCommandPoll } from '@/hooks/useCommandPoll';

const ID_RE = /^[a-z0-9][a-z0-9-]*$/;
const BACKENDS = ['opencode', 'litellm', 'crush'];
const REPO_ROOT = '/home/ai-debian/projects';

export default function NewProjectForm() {
  const router = useRouter();
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [repoPath, setRepoPath] = useState('');
  const [repoTouched, setRepoTouched] = useState(false);
  const [stack, setStack] = useState('python');
  const [backend, setBackend] = useState('opencode');
  const [gitInit, setGitInit] = useState(true);
  const [commandId, setCommandId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const poll = useCommandPoll(commandId);

  const effectiveRepo = repoTouched ? repoPath : id ? `${REPO_ROOT}/${id}` : '';
  const idValid = ID_RE.test(id);
  const busy = poll.phase === 'pending' || poll.phase === 'running';

  useEffect(() => {
    if (poll.phase === 'done') {
      router.push(`/projects/${id}`);
    }
  }, [poll.phase, id, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    try {
      const res = await authedFetch('/api/commands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'new_project',
          project_id: id,
          args: {
            name: name || id,
            repo_path: effectiveRepo,
            stack,
            backend,
            git_init: gitInit,
          },
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.error ?? 'request_failed');
      }
      const { id: cmdId } = await res.json();
      setCommandId(cmdId);
    } catch (err) {
      setSubmitError((err as Error).message);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="max-w-xl space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
    >
      <label className="block text-sm">
        <span className="text-gray-700">ID do projeto *</span>
        <input
          value={id}
          onChange={(e) => setId(e.target.value)}
          placeholder="meu-app"
          required
          autoFocus
          className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm font-mono"
        />
        {id && !idValid && (
          <span className="text-xs text-red-600">
            minúsculas, dígitos e hífens; começa com letra/dígito
          </span>
        )}
      </label>

      <label className="block text-sm">
        <span className="text-gray-700">Nome</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={id || 'Meu App'}
          className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
        />
      </label>

      <label className="block text-sm">
        <span className="text-gray-700">Repositório</span>
        <input
          value={effectiveRepo}
          onChange={(e) => {
            setRepoTouched(true);
            setRepoPath(e.target.value);
          }}
          placeholder={`${REPO_ROOT}/meu-app`}
          className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm font-mono"
        />
      </label>

      <div className="grid grid-cols-2 gap-4">
        <label className="block text-sm">
          <span className="text-gray-700">Stack (csv)</span>
          <input
            value={stack}
            onChange={(e) => setStack(e.target.value)}
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="block text-sm">
          <span className="text-gray-700">Backend</span>
          <select
            value={backend}
            onChange={(e) => setBackend(e.target.value)}
            className="mt-1 w-full rounded border border-gray-300 px-2 py-2 text-sm"
          >
            {BACKENDS.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-700">
        <input
          type="checkbox"
          checked={gitInit}
          onChange={(e) => setGitInit(e.target.checked)}
        />
        Inicializar repositório git (git init + commit vazio)
      </label>

      {submitError && <p className="text-sm text-red-600">{submitError}</p>}
      {busy && (
        <p className="text-sm text-blue-600">
          {poll.phase === 'pending'
            ? 'Aguardando o agente… (se demorar, verifique `squire agent` na VM)'
            : 'Criando projeto…'}
        </p>
      )}
      {poll.phase === 'failed' && (
        <div className="rounded bg-red-50 p-3 text-sm text-red-700">
          <p className="font-medium">Falhou: {poll.error}</p>
          {poll.result?.stderr_tail && (
            <pre className="mt-1 max-h-32 overflow-auto text-xs">{poll.result.stderr_tail}</pre>
          )}
        </div>
      )}
      {poll.phase === 'timeout' && (
        <p className="text-sm text-red-600">
          Sem resposta do agente — confira se `squire agent` está rodando na VM.
        </p>
      )}

      <button
        type="submit"
        disabled={!idValid || busy}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {busy ? 'Criando…' : 'Criar projeto'}
      </button>
    </form>
  );
}
