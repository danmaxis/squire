import { NextRequest, NextResponse } from 'next/server';
import { readJson, writeJsonAtomic } from '@/lib/atomic';
import { requireWriteToken } from '@/lib/auth';
import { projectJsonPath } from '@/lib/squireStatePath';
import { readSessionLock } from '@/lib/squireLock';
import type { Project, ProjectStatus } from '@/lib/types';

const PROJECT_STATUSES: ProjectStatus[] = [
  'planning',
  'implementing',
  'reviewing',
  'blocked',
  'completed',
];
const BACKENDS = ['opencode', 'litellm', 'crush'];

interface PatchProjectBody {
  name?: string;
  description?: string;
  stack?: string[];
  coding_backend?: string | null;
  status?: string;
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const denied = requireWriteToken(req);
  if (denied) return denied;

  const lock = await readSessionLock();
  if (lock.held && lock.holder?.includes(params.id)) {
    return NextResponse.json(
      {
        error: 'squire_running',
        message: `Squire está executando ${params.id} — espere a sessão terminar para editar o projeto.`,
        holder: lock.holder,
      },
      { status: 409 }
    );
  }

  let body: PatchProjectBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const path = projectJsonPath(params.id);
  const project = await readJson<Project>(path);
  if (!project) {
    return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
  }

  const applied: string[] = [];

  if (typeof body.name === 'string' && body.name.trim()) {
    project.name = body.name.trim();
    applied.push('name');
  }
  if (typeof body.description === 'string') {
    project.description = body.description;
    applied.push('description');
  }
  if (Array.isArray(body.stack) && body.stack.every((s) => typeof s === 'string')) {
    project.stack = body.stack.map((s) => s.trim()).filter(Boolean);
    applied.push('stack');
  }
  if (body.coding_backend !== undefined) {
    if (body.coding_backend !== null && !BACKENDS.includes(body.coding_backend)) {
      return NextResponse.json(
        { error: 'invalid_backend', accepts: BACKENDS },
        { status: 400 }
      );
    }
    project.coding_backend = body.coding_backend;
    applied.push('coding_backend');
  }
  if (body.status !== undefined) {
    if (!PROJECT_STATUSES.includes(body.status as ProjectStatus)) {
      return NextResponse.json(
        { error: 'invalid_status', accepts: PROJECT_STATUSES },
        { status: 400 }
      );
    }
    project.status = body.status as ProjectStatus;
    applied.push('status');
  }

  if (applied.length === 0) {
    return NextResponse.json(
      {
        error: 'no_valid_fields',
        accepts: ['name', 'description', 'stack', 'coding_backend', 'status'],
      },
      { status: 400 }
    );
  }

  project.updated_at = new Date().toISOString();
  await writeJsonAtomic(path, project);
  return NextResponse.json({ updated: applied, project });
}
