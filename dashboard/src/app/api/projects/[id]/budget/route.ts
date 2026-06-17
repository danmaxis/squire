import { NextRequest, NextResponse } from 'next/server';
import { readJson, writeJsonAtomic } from '@/lib/atomic';
import { guardProjectWrite } from '@/lib/auth';
import { checkpointPath } from '@/lib/squireStatePath';
import type { Checkpoint } from '@/lib/types';

interface BudgetBody {
  max_daily_usd?: number;
  max_calls_per_window?: number;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const denied = await guardProjectWrite(req, params.id);
  if (denied) return denied;

  let body: BudgetBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const path = checkpointPath(params.id);
  const cp = await readJson<Checkpoint>(path);
  if (!cp) {
    return NextResponse.json({ error: 'checkpoint_not_found' }, { status: 404 });
  }

  const patch: string[] = [];
  if (typeof body.max_daily_usd === 'number' && body.max_daily_usd >= 0) {
    cp.rate_limit.max_daily_usd = body.max_daily_usd;
    patch.push('max_daily_usd');
  }
  if (typeof body.max_calls_per_window === 'number' && body.max_calls_per_window > 0) {
    cp.rate_limit.max_calls_per_window = body.max_calls_per_window;
    patch.push('max_calls_per_window');
  }

  if (patch.length === 0) {
    return NextResponse.json(
      { error: 'no_valid_fields', accepts: ['max_daily_usd', 'max_calls_per_window'] },
      { status: 400 }
    );
  }

  await writeJsonAtomic(path, cp);
  return NextResponse.json({ updated: patch, rate_limit: cp.rate_limit });
}
