import { NextResponse } from 'next/server';

export async function GET(
  request: Request,
  { params }: { params: { id: string } }
) {
  const id = parseInt(params.id, 10);
  const task = { 
    id, 
    name: `Tarefa ${id}`, 
    status: 'running', 
    progress: Math.floor(Math.random() * 100) 
  };
  
  return NextResponse.json(task);
}