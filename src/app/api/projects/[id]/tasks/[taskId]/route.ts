import { NextRequest, NextResponse } from 'next/server';
import { readJson, writeJsonAtomic } from '@/lib/atomic';
import { requireWriteToken } from '@/lib/auth';
import { EDITABLE_TASK_FIELDS, EFFORTS, TEST_AUTHORS } from '@/lib/taskDefaults';
import { tasksPath } from '@/lib/squireStatePath';
import { lockBlocksProject, readSessionLock } from '@/lib/squireLock';
import type { Task, TaskList } from '@/lib/types';

async function guard(req: NextRequest, projectId: string) {
  const denied = requireWriteToken(req);
  if (denied) return denied;

  const lock = await readSessionLock();
  if (lockBlocksProject(lock, projectId)) {
    return NextResponse.json(
      {
        error: 'squire_running',
        message: `Squire está executando ${projectId} — espere a sessão terminar para editar tasks.`,
        holder: lock.holder,
      },
      { status: 409 }
    );
  }
  return null;
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; taskId: string } }
) {
  const denied = await guard(req, params.id);
  if (denied) return denied;

  let body: Partial<Task>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  if (body.effort !== undefined && !EFFORTS.includes(body.effort)) {
    return NextResponse.json({ error: 'invalid_effort', accepts: EFFORTS }, { status: 400 });
  }
  if (body.test_author !== undefined && !TEST_AUTHORS.includes(body.test_author)) {
    return NextResponse.json(
      { error: 'invalid_test_author', accepts: TEST_AUTHORS },
      { status: 400 }
    );
  }

  const path = tasksPath(params.id);
  const taskList = await readJson<TaskList>(path);
  if (!taskList) {
    return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
  }
  const task = taskList.tasks.find((t) => t.id === params.taskId);
  if (!task) {
    return NextResponse.json({ error: 'task_not_found' }, { status: 404 });
  }

  // Aplica somente a whitelist — status/attempts/cost ficam intocados
  const applied: string[] = [];
  const target = task as unknown as Record<string, unknown>;
  for (const field of EDITABLE_TASK_FIELDS) {
    if (field in body && body[field] !== undefined) {
      target[field] = body[field];
      applied.push(field);
    }
  }

  if (applied.length === 0) {
    return NextResponse.json(
      { error: 'no_valid_fields', accepts: EDITABLE_TASK_FIELDS },
      { status: 400 }
    );
  }

  await writeJsonAtomic(path, taskList);
  return NextResponse.json({ updated: applied, task });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string; taskId: string } }
) {
  const denied = await guard(req, params.id);
  if (denied) return denied;

  const path = tasksPath(params.id);
  const taskList = await readJson<TaskList>(path);
  if (!taskList) {
    return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
  }

  const before = taskList.tasks.length;
  taskList.tasks = taskList.tasks.filter((t) => t.id !== params.taskId);
  if (taskList.tasks.length === before) {
    return NextResponse.json({ error: 'task_not_found' }, { status: 404 });
  }

  await writeJsonAtomic(path, taskList);
  return NextResponse.json({ deleted: params.taskId });
}
