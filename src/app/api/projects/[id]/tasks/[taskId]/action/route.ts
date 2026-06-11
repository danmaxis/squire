import { NextRequest, NextResponse } from 'next/server';
import { readJson, writeJsonAtomic } from '@/lib/atomic';
import { requireWriteToken } from '@/lib/auth';
import { tasksPath } from '@/lib/squireStatePath';
import { readSessionLock } from '@/lib/squireLock';
import type { TaskList, Task } from '@/lib/types';

type ActionKind = 'retry' | 'approve' | 'skip';

interface ActionBody {
  action: ActionKind;
}

function applyAction(task: Task, action: ActionKind): Task {
  if (action === 'retry') {
    return {
      ...task,
      attempts: 0,
      homologation_attempt: 0,
      homologation_result: null,
      no_progress_streak: 0,
      rejection_summaries: [],
      status: 'pending',
    };
  }
  if (action === 'approve') {
    return {
      ...task,
      homologation_result: 'approved',
      status: 'completed',
      completed_at: new Date().toISOString(),
    };
  }
  // skip
  return {
    ...task,
    skip_homologation: true,
    status: 'pending',
  };
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string; taskId: string } }
) {
  const denied = requireWriteToken(req);
  if (denied) return denied;

  const { id: projectId, taskId } = params;

  const lock = await readSessionLock();
  if (lock.held && lock.holder?.includes(projectId)) {
    return NextResponse.json(
      {
        error: 'squire_running',
        message: `Squire está ativamente executando ${projectId} (holder=${lock.holder}). Espere a sessão terminar.`,
        holder: lock.holder,
        pid: lock.pid,
      },
      { status: 409 }
    );
  }

  let body: ActionBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  if (!body.action || !['retry', 'approve', 'skip'].includes(body.action)) {
    return NextResponse.json(
      { error: 'invalid_action', accepts: ['retry', 'approve', 'skip'] },
      { status: 400 }
    );
  }

  const path = tasksPath(projectId);
  const list = await readJson<TaskList>(path);
  if (!list) {
    return NextResponse.json({ error: 'tasks_not_found' }, { status: 404 });
  }

  let touched = false;
  list.tasks = list.tasks.map((t) => {
    if (t.id !== taskId) return t;
    touched = true;
    return applyAction(t, body.action);
  });

  if (!touched) {
    return NextResponse.json({ error: 'task_not_found', task_id: taskId }, { status: 404 });
  }

  await writeJsonAtomic(path, list);
  return NextResponse.json({ action: body.action, task_id: taskId });
}
