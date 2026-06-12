import { NextRequest, NextResponse } from 'next/server';
import { requireWriteToken } from '@/lib/auth';

// Valida o token do usuário (usado pela página /login).
export async function GET(req: NextRequest) {
  const denied = requireWriteToken(req);
  if (denied) return denied;
  return new NextResponse(null, { status: 204 });
}
