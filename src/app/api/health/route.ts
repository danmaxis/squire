import { NextResponse } from 'next/server';

// Sem request object o Next otimiza o handler para estático e congela o
// timestamp do build — force dynamic para o healthcheck ser real.
export const dynamic = 'force-dynamic';

export async function GET() {
  // Endpoint de saúde para teste de polling
  return NextResponse.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    message: 'Servidor saudável'
  });
}