import React from 'react';

interface ProjectCardProps {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'completed' | 'on-hold' | 'failed' | 'blocked';
  completedTasks: number;
  totalTasks: number;
  /** Tasks bloqueadas — badge vermelho quando > 0. */
  blockedTasks?: number;
  lastUpdated: Date;
}

const getStatusColor = (status: ProjectCardProps['status']) => {
  switch (status) {
    case 'active':
      return 'bg-green-100 text-green-800 border-green-200';
    case 'completed':
      return 'bg-blue-100 text-blue-800 border-blue-200';
    case 'on-hold':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'blocked':
    case 'failed':
      return 'bg-red-100 text-red-800 border-red-200';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200';
  }
};

const getStatusLabel = (status: ProjectCardProps['status']) => {
  switch (status) {
    case 'active': return 'Ativo';
    case 'completed': return 'Concluído';
    case 'on-hold': return 'Pausado';
    case 'blocked': return 'Bloqueado';
    case 'failed': return 'Falhou';
    default: return 'Desconhecido';
  }
};

const formatTimeAgo = (date: Date): string => {
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) return 'Agora mesmo';
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutos atrás`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} horas atrás`;
  return `${Math.floor(diffInSeconds / 86400)} dias atrás`;
};

export const ProjectCard: React.FC<ProjectCardProps> = ({
  name,
  description,
  status,
  completedTasks,
  totalTasks,
  blockedTasks = 0,
  lastUpdated,
}) => {
  const progressPercentage = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
  
  // Truncar descrição se for muito longa
  const truncatedDescription = description.length > 100 
    ? `${description.substring(0, 100)}...` 
    : description;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 hover:shadow-md transition-shadow duration-200">
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-lg font-semibold text-gray-900 truncate pr-2" title={name}>
          {name}
        </h3>
        <span className="flex items-center gap-1.5">
          {blockedTasks > 0 && (
            <span
              className="px-2 py-0.5 rounded-full text-xs font-medium border bg-red-100 text-red-800 border-red-200"
              title="Tasks bloqueadas aguardando triagem"
            >
              {blockedTasks} bloqueada{blockedTasks > 1 ? 's' : ''}
            </span>
          )}
          <span
            className={`px-2.5 py-0.5 rounded-full text-xs font-medium border ${getStatusColor(status)}`}
          >
            {getStatusLabel(status)}
          </span>
        </span>
      </div>

      <p className="text-sm text-gray-600 mb-4 line-clamp-2" title={description}>
        {truncatedDescription}
      </p>

      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Progresso</span>
          <span>{completedTasks} / {totalTasks} ({progressPercentage}%)</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-indigo-600 h-2 rounded-full transition-all duration-500"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      <div className="flex items-center text-xs text-gray-400">
        <svg
          className="w-4 h-4 mr-1.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        Última atualização: {formatTimeAgo(lastUpdated)}
      </div>
    </div>
  );
};