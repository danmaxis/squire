import { promises as fs } from 'fs';
import { dirname, join } from 'path';

/**
 * Atomic JSON write: serialize → write to .tmp sibling → rename over target.
 * Matches the pattern squire's checkpoint.atomic_write_json uses, so writes
 * from the dashboard and writes from squire never interleave into a torn file.
 *
 * `rename` is atomic on the same filesystem; both squire-state and the
 * container's view of it live on one filesystem so this holds.
 */
export async function writeJsonAtomic(
  path: string,
  data: unknown,
  { pretty = true }: { pretty?: boolean } = {}
): Promise<void> {
  const dir = dirname(path);
  await fs.mkdir(dir, { recursive: true });

  const body = pretty ? JSON.stringify(data, null, 2) : JSON.stringify(data);
  const tmp = join(dir, `.${process.pid}-${Date.now()}.tmp`);

  try {
    await fs.writeFile(tmp, body, 'utf-8');
    await fs.rename(tmp, path);
  } catch (err) {
    try {
      await fs.unlink(tmp);
    } catch {
      /* ignore */
    }
    throw err;
  }
}

/**
 * Read JSON and return null when missing. Used as the "read part" of the
 * read-mutate-write pattern in the API routes.
 */
export async function readJson<T>(path: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(path, 'utf-8');
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}
