import { NextRequest, NextResponse } from 'next/server';
import { readJson, writeJsonAtomic } from '@/lib/atomic';
import { alertsPath } from '@/lib/squireStatePath';
import type { AlertList } from '@/lib/types';

interface AckBody {
  project_id: string;
  task_id: string | null;
  created_at: string;
  dismiss?: boolean;
}

function matchesAlert(
  alert: AlertList['alerts'][number],
  body: AckBody
): boolean {
  return (
    alert.project_id === body.project_id &&
    (alert.task_id ?? null) === (body.task_id ?? null) &&
    alert.created_at === body.created_at
  );
}

export async function POST(req: NextRequest) {
  let body: AckBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  if (!body.project_id || !body.created_at) {
    return NextResponse.json(
      { error: 'missing_fields', required: ['project_id', 'created_at'] },
      { status: 400 }
    );
  }

  const path = alertsPath();
  const list = (await readJson<AlertList>(path)) ?? { alerts: [] };

  let updated = 0;
  if (body.dismiss) {
    const before = list.alerts.length;
    list.alerts = list.alerts.filter((a) => !matchesAlert(a, body));
    updated = before - list.alerts.length;
  } else {
    list.alerts = list.alerts.map((a) => {
      if (matchesAlert(a, body)) {
        updated += 1;
        return { ...a, acknowledged: true };
      }
      return a;
    });
  }

  if (updated === 0) {
    return NextResponse.json({ error: 'alert_not_found' }, { status: 404 });
  }

  await writeJsonAtomic(path, list);
  return NextResponse.json({ updated, dismissed: !!body.dismiss });
}
