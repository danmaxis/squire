import { NextRequest, NextResponse } from 'next/server';
import { readJson, writeJsonAtomic } from '@/lib/atomic';
import { requireWriteToken } from '@/lib/auth';
import { newTask, nextTaskId, EFFORTS, TEST_AUTHORS } from '@/lib/taskDefaults';
import { tasksPath } from '@/lib/squireStatePath';
import { readSessionLock } from '@/lib/squireLock';
import type { TaskList } from '@/lib/types';

interface CreateTaskBody {
  id?: string;
  title?: string;
  description?: string;
  effort?: string;
  tdd?: boolean;
  test_author?: string;
  skip_homologation?: boolean;
  max_attempts?: number;
  max_homologation_attempts?: number;
  max_usd?: number | null;
}

export async function POST(
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
        message: `Squire está executando ${params.id} — espere a sessão terminar para criar tasks.`,
        holder: lock.holder,
      },
      { status: 409 }
    );
  }

  let body: CreateTaskBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  if (!body.title || !body.title.trim()) {
    return NextResponse.json(
      { error: 'missing_fields', required: ['title'] },
      { status: 400 }
    );
  }
  if (body.effort !== undefined && !EFFORTS.includes(body.effort as never)) {
    return NextResponse.json(
      { error: 'invalid_effort', accepts: EFFORTS },
      { status: 400 }
    );
  }
  if (
    body.test_author !== undefined &&
    !TEST_AUTHORS.includes(body.test_author as never)
  ) {
    return NextResponse.json(
      { error: 'invalid_test_author', accepts: TEST_AUTHORS },
      { status: 400 }
    );
  }

  const path = tasksPath(params.id);
  const taskList = (await readJson<TaskList>(path)) ?? null;
  if (!taskList) {
    return NextResponse.json({ error: 'project_not_found' }, { status: 404 });
  }

  const id = body.id?.trim() || nextTaskId(taskList);
  if (taskList.tasks.some((t) => t.id === id)) {
    return NextResponse.json({ error: 'duplicate_id', id }, { status: 409 });
  }

  const task = newTask({
    id,
    title: body.title.trim(),
    description: body.description,
    effort: body.effort as never,
    tdd: body.tdd,
    test_author: body.test_author as never,
    skip_homologation: body.skip_homologation,
    max_attempts: body.max_attempts,
    max_homologation_attempts: body.max_homologation_attempts,
    max_usd: body.max_usd,
  });

  taskList.tasks.push(task);
  await writeJsonAtomic(path, taskList);
  return NextResponse.json({ created: task }, { status: 201 });
}
