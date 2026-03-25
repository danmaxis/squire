'use client';

import React, { useEffect, useState } from 'react';

interface GlobalStatsData {
  active_projects: number;
  tasks_completed_today: number;
  llm_calls: {
    local: number;
    claude_code: number;
  };
  first_approval_rate: number;
}

const GlobalStats: React.FC = () => {
  const [stats, setStats] = useState<GlobalStatsData>({
    active_projects: 0,
    tasks_completed_today: 0,
    llm_calls: { local: 0, claude_code: 0 },
    first_approval_rate: 0,
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('/global-stats.json');
        if (!response.ok) {
          // Se o arquivo não existir ou der erro, mantemos os zeros iniciais
          return;
        }
        const data = await response.json();
        setStats(data);
      } catch (error) {
        console.warn('Falha ao carregar global-stats.json, usando valores padrão.', error);
      }
    };

    fetchStats();
  }, []);

  const totalLlmCalls = stats.llm_calls.local + stats.llm_calls.claude_code;
  const localPercentage = totalLlmCalls > 0 
    ? Math.round((stats.llm_calls.local / totalLlmCalls) * 100) 
    : 0;
  const claudePercentage = totalLlmCalls > 0 
    ? Math.round((stats.llm_calls.claude_code / totalLlmCalls) * 100) 
    : 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Card: Projetos Ativos */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 flex items-center space-x-4 border border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-blue-100 dark:bg-blue-900 rounded-full text-blue-600 dark:text-blue-300">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Projetos Ativos</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.active_projects}</p>
        </div>
      </div>

      {/* Card: Tasks Completas Hoje */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 flex items-center space-x-4 border border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-green-100 dark:bg-green-900 rounded-full text-green-600 dark:text-green-300">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Tasks Completas Hoje</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">{stats.tasks_completed_today}</p>
        </div>
      </div>

      {/* Card: Chamadas LLM (Local vs Claude) */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 flex items-center space-x-4 border border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-purple-100 dark:bg-purple-900 rounded-full text-purple-600 dark:text-purple-300">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <div className="flex-1">
          <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Chamadas LLM</p>
          <div className="flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">
              {stats.llm_calls.local + stats.llm_calls.claude_code}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              ({localPercentage}% Local, {claudePercentage}% Claude)
            </span>
          </div>
        </div>
      </div>

      {/* Card: Taxa de Aprovação 1ª Homologação */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4 flex items-center space-x-4 border border-gray-200 dark:border-gray-700">
        <div className="p-3 bg-yellow-100 dark:bg-yellow-900 rounded-full text-yellow-600 dark:text-yellow-300">
          <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
          </svg>
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">Aprovação 1ª Homologação</p>
          <p className="text-2xl font-bold text-gray-900 dark:text-white">
            {stats.first_approval_rate}%
          </p>
        </div>
      </div>
    </div>
  );
};

export default GlobalStats;