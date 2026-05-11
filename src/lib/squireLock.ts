import { promises as fs } from 'fs';
import { join } from 'path';
import { readJson } from './atomic';

const DATA_PATH =
  process.env.SQUIRE_DATA_PATH ?? join(process.cwd(), 'fixtures', 'data');

interface SessionLockJson {
  holder: string;
  acquired_at: string;
  ttl_minutes: number;
  pid: number;
}

export interface LockStatus {
  /** True when a fresh lock file (mtime + TTL window) exists. */
  held: boolean;
  holder: string | null;
  pid: number | null;
  acquiredAt: string | null;
  /** Seconds since the lock file was last modified. null when no lock. */
  ageSeconds: number | null;
}

/**
 * Inspect /home/ai-debian/squire-state/session.lock and report whether a
 * squire run is currently active. The mutation API routes use this to refuse
 * a write that would race a writer.
 *
 * The TTL field on the lock model is the same one squire enforces; we read
 * it back and treat the lock as stale once exceeded.
 */
export async function readSessionLock(): Promise<LockStatus> {
  const path = join(DATA_PATH, 'session.lock');
  let stat;
  try {
    stat = await fs.stat(path);
  } catch {
    return { held: false, holder: null, pid: null, acquiredAt: null, ageSeconds: null };
  }

  const data = await readJson<SessionLockJson>(path);
  if (!data) {
    return { held: false, holder: null, pid: null, acquiredAt: null, ageSeconds: null };
  }

  const ageSeconds = (Date.now() - stat.mtimeMs) / 1000;
  const ttlSeconds = (data.ttl_minutes ?? 60) * 60;
  const held = ageSeconds < ttlSeconds;

  return {
    held,
    holder: data.holder ?? null,
    pid: data.pid ?? null,
    acquiredAt: data.acquired_at ?? null,
    ageSeconds,
  };
}
