import { NextRequest, NextResponse } from 'next/server';
import { requireWriteToken } from '@/lib/auth';
import { enqueueCommand } from '@/lib/commands';
import { readSessionLock } from '@/lib/squireLock';
import type { CommandType } from '@/lib/types';

/**
 * Enfileira um comando para o agente host. A validação aqui espelha a do
 * agente (que valida de novo — não confiamos só no dashboard); o objetivo
 * é falhar cedo com mensagens claras na UI.
 */

const COMMAND_TYPES: CommandType[] = [
  'new_project',
  'run',
  'resume',
  'kill',
  'plan_tasks',
  'split_task',
];
const PROJECT_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
const TASK_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
const BACKENDS = ['opencode', 'litellm', 'crush'];

interface EnqueueBody {
  type?: CommandType;
  project_id?: string | null;
  args?: Record<string, unknown>;
}

function validationError(body: EnqueueBody): string | null {
  const { type, project_id: projectId, args = {} } = body;

  if (!type || !COMMAND_TYPES.includes(type)) {
    return `type deve ser um de: ${COMMAND_TYPES.join(', ')}`;
  }
  if (type !== 'kill') {
    if (!projectId || !PROJECT_ID_RE.test(projectId)) {
      return 'project_id inválido (minúsculas, dígitos e hífens)';
    }
  }
  if (type === 'new_project') {
    const backend = (args.backend as string) ?? 'opencode';
    if (!BACKENDS.includes(backend)) {
      return `backend deve ser um de: ${BACKENDS.join(', ')}`;
    }
  }
  if (type === 'plan_tasks') {
    const mode = (args.mode as string) ?? 'append';
    if (!['append', 'replace'].includes(mode)) {
      return "mode deve ser 'append' ou 'replace'";
    }
  }
  if (type === 'split_task') {
    if (!TASK_ID_RE.test((args.task_id as string) ?? '')) {
      return 'task_id inválido';
    }
  }
  return null;
}

export async function POST(req: NextRequest) {
  const denied = requireWriteToken(req);
  if (denied) return denied;

  let body: EnqueueBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const problem = validationError(body);
  if (problem) {
    return NextResponse.json({ error: 'invalid_command', message: problem }, { status: 400 });
  }

  // Pré-check de lock para run/resume: melhor 409 imediato na UI do que
  // um comando que falha no agente segundos depois.
  if (body.type === 'run' || body.type === 'resume') {
    const lock = await readSessionLock();
    if (lock.held) {
      return NextResponse.json(
        {
          error: 'squire_running',
          message: `Já existe uma sessão ativa (${lock.holder}). Espere terminar ou use Kill.`,
          holder: lock.holder,
        },
        { status: 409 }
      );
    }
  }

  const cmd = await enqueueCommand(
    body.type!,
    body.type === 'kill' ? null : body.project_id!,
    body.args ?? {}
  );
  return NextResponse.json({ id: cmd.id }, { status: 202 });
}
