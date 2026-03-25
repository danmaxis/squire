import { NextResponse } from 'next/server';

export async function GET() {
  // Endpoint de saúde para teste de polling
  return NextResponse.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    message: 'Servidor saudável'
  });
}