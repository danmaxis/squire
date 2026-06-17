import { timingSafeEqual } from 'crypto';
import { NextRequest, NextResponse } from 'next/server';
import { lockBlocksProject, readSessionLock } from './squireLock';

/**
 * Gate de escrita por token compartilhado.
 *
 * Lê DASHBOARD_WRITE_TOKEN a cada chamada (não em module-load) para que
 * testes possam stubar o env. Sem o token configurado no servidor, toda
 * escrita responde 503 — opt-in explícito, nunca escrita aberta por engano.
 *
 * Uso no topo de cada handler mutante:
 *   const denied = requireWriteToken(req);
 *   if (denied) return denied;
 */
export function requireWriteToken(req: NextRequest): NextResponse | null {
  const expected = process.env.DASHBOARD_WRITE_TOKEN;
  if (!expected) {
    return NextResponse.json(
      {
        error: 'writes_disabled',
        message: 'DASHBOARD_WRITE_TOKEN não configurado no servidor',
      },
      { status: 503 }
    );
  }

  const header = req.headers.get('authorization') ?? '';
  const provided = header.startsWith('Bearer ') ? header.slice(7) : '';

  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  const valid = a.length === b.length && timingSafeEqual(a, b);

  if (!valid) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  return null;
}

/**
 * Guard composto para rotas que mutam estado de um projeto:
 * token válido (401/503) + sessão squire não pode estar executando o
 * projeto (409). Retorna null quando a escrita pode prosseguir.
 */
export async function guardProjectWrite(
  req: NextRequest,
  projectId: string
): Promise<NextResponse | null> {
  const denied = requireWriteToken(req);
  if (denied) return denied;

  const lock = await readSessionLock();
  if (lockBlocksProject(lock, projectId)) {
    return NextResponse.json(
      {
        error: 'squire_running',
        message: `Squire está executando ${projectId} (holder=${lock.holder}) — espere a sessão terminar.`,
        holder: lock.holder,
        pid: lock.pid,
      },
      { status: 409 }
    );
  }
  return null;
}
