'use client';

import { useState } from 'react';

interface Subtask {
  id: string;
  title: string;
  status: string;
}

interface Task {
  id: string;
  title: string;
  status: string;
  attempts: number;
  homologationResult: string;
  subtasks: Subtask[];
}

interface TaskListProps {
  tasks: Task[];
}

const getStatusColor = (status: string) => {
  switch (status.toLowerCase()) {
    case 'concluído': return 'text-green-600 bg-green-50';
    case 'em andamento': 
    case 'em progresso': return 'text-blue-600 bg-blue-50';
    case 'em revisão': return 'text-yellow-600 bg-yellow-50';
    case 'bloqueado': return 'text-red-600 bg-red-50';
    default: return 'text-gray-600 bg-gray-50';
  }
};

export default function TaskList({ tasks }: TaskListProps) {
  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());

  const toggleExpand = (taskId: string) => {
    const newExpanded = new Set(expandedTasks);
    if (newExpanded.has(taskId)) {
      newExpanded.delete(taskId);
    } else {
      newExpanded.add(taskId);
    }
    setExpandedTasks(newExpanded);
  };

  return (
    <div className="space-y-4">
      {tasks.map((task) => (
        <div 
          key={task.id} 
          className="border border-gray-200 rounded-lg overflow-hidden transition-all duration-200 hover:shadow-md"
        >
          {/* Cabeçalho da Task */}
          <div 
            className="p-4 flex items-center justify-between cursor-pointer bg-gray-50 hover:bg-gray-100"
            onClick={() => toggleExpand(task.id)}
          >
            <div className="flex items-center gap-3">
              <div className={`w-3 h-3 rounded-full ${
                task.status.toLowerCase() === 'concluído' ? 'bg-green-500' :
                task.status.toLowerCase() === 'bloqueado' ? 'bg-red-500' :
                'bg-blue-500'
              }`} />
              <h3 className="font-semibold text-gray-800">{task.title}</h3>
            </div>
            
            <div className="flex items-center gap-4 text-sm">
              <div className="flex flex-col items-end">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusColor(task.status)}`}>
                  {task.status}
                </span>
                <span className="text-xs text-gray-500 mt-1">
                  {task.homologationResult}
                </span>
              </div>
              <button className="text-gray-400 hover:text-gray-600">
                {expandedTasks.has(task.id) ? '▲' : '▼'}
              </button>
            </div>
          </div>

          {/* Detalhes Expansíveis */}
          {expandedTasks.has(task.id) && (
            <div className="p-4 bg-white border-t border-gray-100 animate-fadeIn">
              <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-500">Tentativas:</span>
                  <span className="text-gray-800 font-mono">{task.attempts}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-500">Homologação:</span>
                  <span className={`font-medium ${
                    task.homologationResult === 'Aprovado' ? 'text-green-600' :
                    task.homologationResult === 'Reprovado' ? 'text-red-600' :
                    'text-gray-600'
                  }`}>
                    {task.homologationResult}
                  </span>
                </div>
              </div>

              {task.subtasks.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                    Subtarefas
                  </h4>
                  <ul className="space-y-2">
                    {task.subtasks.map((subtask) => (
                      <li key={subtask.id} className="flex items-center gap-2 text-sm">
                        <div className={`w-2 h-2 rounded-full ${
                          subtask.status.toLowerCase() === 'concluído' ? 'bg-green-400' : 'bg-gray-300'
                        }`} />
                        <span className={subtask.status.toLowerCase() === 'concluído' ? 'text-gray-600 line-through' : 'text-gray-800'}>
                          {subtask.title}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}