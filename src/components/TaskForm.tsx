'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { authedFetch } from '@/lib/clientApi';
import { EFFORTS, TEST_AUTHORS } from '@/lib/taskDefaults';
import type { Effort, Task, TestAuthor } from '@/lib/types';

interface TaskFormProps {
  projectId: string;
  /** Task existente = modo edição; ausente = criação. */
  task?: Task;
  onClose: () => void;
}

export default function TaskForm({ projectId, task, onClose }: TaskFormProps) {
  const router = useRouter();
  const editing = Boolean(task);

  const [title, setTitle] = useState(task?.title ?? '');
  const [description, setDescription] = useState(task?.description ?? '');
  const [effort, setEffort] = useState<Effort>(task?.effort ?? 'medium');
  const [tdd, setTdd] = useState(task?.tdd ?? true);
  const [testAuthor, setTestAuthor] = useState<TestAuthor>(task?.test_author ?? 'claude');
  const [skipHomolog, setSkipHomolog] = useState(task?.skip_homologation ?? false);
  const [maxAttempts, setMaxAttempts] = useState(task?.max_attempts ?? 10);
  const [maxHomolog, setMaxHomolog] = useState(task?.max_homologation_attempts ?? 5);
  const [maxUsd, setMaxUsd] = useState<string>(task?.max_usd?.toString() ?? '');

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const payload = {
      title,
      description,
      effort,
      tdd,
      test_author: testAuthor,
      skip_homologation: skipHomolog,
      max_attempts: maxAttempts,
      max_homologation_attempts: maxHomolog,
      max_usd: maxUsd.trim() === '' ? null : Number(maxUsd),
    };
    try {
      const res = await authedFetch(
        editing
          ? `/api/projects/${projectId}/tasks/${task!.id}`
          : `/api/projects/${projectId}/tasks`,
        {
          method: editing ? 'PATCH' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.message ?? body.error ?? 'request_failed');
      }
      router.refresh();
      onClose();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg space-y-4 rounded-lg bg-white p-6 shadow-xl max-h-[90vh] overflow-y-auto"
      >
        <h2 className="text-lg font-semibold text-gray-800">
          {editing ? `Editar ${task!.id}` : 'Nova task'}
        </h2>

        <label className="block text-sm">
          <span className="text-gray-700">Título *</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>

        <label className="block text-sm">
          <span className="text-gray-700">Descrição</span>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Seja específico: quais arquivos criar, comportamento esperado, quais testes devem passar."
            className="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
        </label>

        <div className="grid grid-cols-2 gap-4">
          <label className="block text-sm">
            <span className="text-gray-700">Effort</span>
            <select
              value={effort}
              onChange={(e) => setEffort(e.target.value as Effort)}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-2 text-sm"
            >
              {EFFORTS.map((ef) => (
                <option key={ef} value={ef}>{ef}</option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="text-gray-700">Autor dos testes</span>
            <select
              value={testAuthor}
              onChange={(e) => setTestAuthor(e.target.value as TestAuthor)}
              disabled={!tdd}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-400"
            >
              {TEST_AUTHORS.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex gap-6 text-sm">
          <label className="flex items-center gap-2 text-gray-700">
            <input type="checkbox" checked={tdd} onChange={(e) => setTdd(e.target.checked)} />
            TDD (fase RED antes do inner loop)
          </label>
          <label className="flex items-center gap-2 text-gray-700">
            <input
              type="checkbox"
              checked={skipHomolog}
              onChange={(e) => setSkipHomolog(e.target.checked)}
            />
            Pular homologação
          </label>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <label className="block text-sm">
            <span className="text-gray-700">Max tentativas</span>
            <input
              type="number"
              min={1}
              value={maxAttempts}
              onChange={(e) => setMaxAttempts(Number(e.target.value))}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-gray-700">Max rodadas</span>
            <input
              type="number"
              min={1}
              value={maxHomolog}
              onChange={(e) => setMaxHomolog(Number(e.target.value))}
              className="mt-1 w-full rounded border border-gray-300 px-2 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-gray-700">Cap USD</span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={maxUsd}
              onChange={(e) => setMaxUsd(e.target.value)}
              placeholder="sem cap"
              className="mt-1 w-full rounded border border-gray-300 px-2 py-2 text-sm"
            />
          </label>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded px-4 py-2 text-sm text-gray-600 hover:bg-gray-100"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving || !title.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {saving ? 'Salvando…' : editing ? 'Salvar' : 'Criar task'}
          </button>
        </div>
      </form>
    </div>
  );
}
