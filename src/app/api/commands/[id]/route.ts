import { NextRequest, NextResponse } from 'next/server';
import { requireWriteToken } from '@/lib/auth';
import { getCommandStatus } from '@/lib/commands';

// UUID v4 — também serve de guarda contra path traversal no nome do arquivo
const ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  // Resultados carregam stdout do host — exigem o mesmo token das escritas
  const denied = requireWriteToken(req);
  if (denied) return denied;

  if (!ID_RE.test(params.id)) {
    return NextResponse.json({ error: 'invalid_id' }, { status: 400 });
  }

  const view = await getCommandStatus(params.id);
  if (!view) {
    // desconhecido ou resultado expirado pelo TTL do agente
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
  return NextResponse.json(view);
}
