import { NextResponse } from 'next/server';

// Simulação de dados de tarefas
const tasks = [
  { id: 1, name: 'Processamento de Lote A', status: 'running', progress: 45 },
  { id: 2, name: 'Sincronização de Banco', status: 'completed', progress: 100 },
  { id: 3, name: 'Backup Noturno', status: 'pending', progress: 0 },
];

export async function GET() {
  // Retorna dados com timestamp para forçar revalidação se necessário
  return NextResponse.json({ 
    tasks, 
    lastUpdated: new Date().toISOString() 
  });
}