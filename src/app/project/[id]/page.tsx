'use client';

import { useParams } from 'next/navigation';
import { useState } from 'react';
import TaskList from '@/components/TaskList';
import Timeline from '@/components/Timeline';

// Mock data para simulação (em produção, isso viria de uma API ou contexto)
const MOCK_PROJECT = {
  id: '1',
  name: 'Refatoração do Core de Pagamentos',
  status: 'Em Progresso',
  description: 'Projeto focado na modernização do sistema de pagamentos, garantindo maior escalabilidade e segurança nas transações.',
  tasks: [
    {
      id: 't1',
      title: 'Implementar Gateway de Pagamento',
      status: 'Concluído',
      attempts: 2,
      homologationResult: 'Aprovado',
      subtasks: [
        { id: 'st1', title: 'Configurar API Key', status: 'Concluído' },
        { id: 'st2', title: 'Testar transações de teste', status: 'Concluído' },
      ]
    },
    {
      id: 't2',
      title: 'Integração com Antifraude',
      status: 'Em Revisão',
      attempts: 1,
      homologationResult: 'Pendente',
      subtasks: [
        { id: 'st3', title: 'Mapear endpoints de risco', status: 'Concluído' },
        { id: 'st4', title: 'Implementar lógica de bloqueio', status: 'Em andamento' },
      ]
    },
    {
      id: 't3',
      title: 'Relatórios Financeiros',
      status: 'Bloqueado',
      attempts: 0,
      homologationResult: 'Não Iniciado',
      subtasks: []
    }
  ],
  history: [
    { id: 'h1', type: 'DEPLOY', actor: 'DevOps', date: '2023-10-25T14:30:00', message: 'Deploy da versão 2.1.0 em produção' },
    { id: 'h2', type: 'BUG', actor: 'QA', date: '2023-10-24T09:15:00', message: 'Bug crítico identificado na validação de CPF' },
    { id: 'h3', type: 'FEATURE', actor: 'Dev Lead', date: '2023-10-23T16:00:00', message: 'Revisão de código da feature de PIX concluída' },
    { id: 'h4', type: 'MEETING', actor: 'Product Owner', date: '2023-10-22T10:00:00', message: 'Reunião de alinhamento de sprint' },
  ]
};

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params.id as string;

  // Simulação de carregamento de dados
  const [project, setProject] = useState(MOCK_PROJECT);

  if (!project) {
    return <div className="p-8 text-center">Carregando detalhes do projeto...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Cabeçalho do Projeto */}
      <header className="bg-white rounded-lg shadow-sm p-6 mb-6 border-l-4 border-blue-500">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold text-gray-800 mb-2">{project.name}</h1>
            <p className="text-gray-600 text-lg">{project.description}</p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <span 
              className={`px-4 py-1 rounded-full text-sm font-semibold ${
                project.status === 'Em Progresso' ? 'bg-blue-100 text-blue-800' :
                project.status === 'Concluído' ? 'bg-green-100 text-green-800' :
                project.status === 'Bloqueado' ? 'bg-red-100 text-red-800' :
                'bg-gray-100 text-gray-800'
              }`}
            >
              {project.status}
            </span>
            <span className="text-xs text-gray-400">ID: {project.id}</span>
          </div>
        </div>
      </header>

      {/* Layout Principal: TaskList e Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Coluna Esquerda: TaskList */}
        <section className="bg-white rounded-lg shadow-sm p-6 h-fit">
          <h2 className="text-xl font-bold text-gray-800 mb-4 border-b pb-2">
            Lista de Tarefas ({project.tasks.length})
          </h2>
          <TaskList tasks={project.tasks} />
        </section>

        {/* Coluna Direita: Timeline */}
        <section className="bg-white rounded-lg shadow-sm p-6 h-fit">
          <h2 className="text-xl font-bold text-gray-800 mb-4 border-b pb-2">
            Histórico do Projeto
          </h2>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          <Timeline events={project.history as any} />
        </section>
      </div>
    </div>
  );
}