import { promises as fs } from 'fs';
import { join } from 'path';
import { readJson } from './atomic';
import { DATA_PATH } from './squireStatePath';

interface SessionLockJson {
  holder: string;
  project_id?: string | null;
  acquired_at: string;
  ttl_minutes: number;
  pid: number;
}

export interface LockStatus {
  /** True when a fresh lock file (mtime + TTL window) exists. */
  held: boolean;
  holder: string | null;
  /** Projeto sendo executado pela sessão (campo estruturado do lock). */
  projectId: string | null;
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
  const empty: LockStatus = {
    held: false,
    holder: null,
    projectId: null,
    pid: null,
    acquiredAt: null,
    ageSeconds: null,
  };

  let stat;
  try {
    stat = await fs.stat(path);
  } catch {
    return empty;
  }

  const data = await readJson<SessionLockJson>(path);
  if (!data) {
    return empty;
  }

  const ageSeconds = (Date.now() - stat.mtimeMs) / 1000;
  const ttlSeconds = (data.ttl_minutes ?? 60) * 60;
  const held = ageSeconds < ttlSeconds;

  return {
    held,
    holder: data.holder ?? null,
    projectId: data.project_id ?? null,
    pid: data.pid ?? null,
    acquiredAt: data.acquired_at ?? null,
    ageSeconds,
  };
}

/**
 * O lock bloqueia escritas neste projeto? Escritas em arquivos de OUTRO
 * projeto são seguras — o squire só grava os arquivos do projeto que está
 * executando. Locks antigos sem project_id estruturado bloqueiam por
 * precaução.
 */
export function lockBlocksProject(lock: LockStatus, projectId: string): boolean {
  if (!lock.held) return false;
  if (lock.projectId == null) return true; // lock antigo sem campo — conservador
  return lock.projectId === projectId;
}
