'use client';

import React, { useState } from 'react';
import { CommitSummary } from '@/lib/types';

interface CommitLogProps {
  commits: CommitSummary[];
  pageSize?: number;
  isLoading?: boolean;
}

const getRelativeTime = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) return 'há alguns segundos';
  if (diffInSeconds < 3600) return `há ${Math.floor(diffInSeconds / 60)} minuto(s)`;
  if (diffInSeconds < 86400) return `há ${Math.floor(diffInSeconds / 3600)} hora(s)`;
  if (diffInSeconds < 604800) return `há ${Math.floor(diffInSeconds / 86400)} dia(s)`;

  return date.toLocaleDateString('pt-BR');
};

const truncateSha = (sha: string): string => sha.substring(0, 7);

const FILES_PREVIEW = 3;

export const CommitLog: React.FC<CommitLogProps> = ({ commits, pageSize = 20, isLoading = false }) => {
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());

  const toggleFiles = (key: string) =>
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const displayedCommits = commits.slice(0, visibleCount);
  const remaining = commits.length - visibleCount;

  if (isLoading) {
    return (
      <div className="p-4 text-center text-gray-500 animate-pulse">
        Carregando histórico de commits...
      </div>
    );
  }

  if (!commits || commits.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
        <p className="text-lg font-medium">Nenhum commit encontrado</p>
        <p className="text-sm mt-1">O projeto ainda não possui histórico de alterações.</p>
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="space-y-4">
        {displayedCommits.map((commit, index) => (
          <div
            key={`${commit.sha}-${index}`}
            className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                  {truncateSha(commit.sha)}
                </span>
                <span className="text-xs text-gray-400">
                  {getRelativeTime(commit.timestamp)}
                </span>
              </div>
            </div>

            <h3 className="text-gray-900 font-medium mb-1 leading-tight">
              {commit.message}
            </h3>

            {commit.diff_summary && (
              <p className="text-sm text-gray-600 mb-3 bg-blue-50 p-2 rounded border-l-4 border-blue-400">
                {commit.diff_summary}
              </p>
            )}

            {commit.files_changed && commit.files_changed.length > 0 && (() => {
              const fileKey = `${commit.sha}-${index}`;
              const isExpanded = expandedFiles.has(fileKey);
              const hasMore = commit.files_changed.length > FILES_PREVIEW;
              const visibleFiles = isExpanded
                ? commit.files_changed
                : commit.files_changed.slice(0, FILES_PREVIEW);
              return (
                <div className="mt-3">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                    Arquivos alterados
                  </h4>
                  <ul className="space-y-1">
                    {visibleFiles.map((file, fileIndex) => (
                      <li key={fileIndex} className="flex items-center text-sm text-gray-700">
                        <span className="w-1.5 h-1.5 bg-gray-300 rounded-full mr-2"></span>
                        <span className="font-mono text-xs truncate max-w-[200px] sm:max-w-[300px]">
                          {file}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {hasMore && (
                    <button
                      onClick={() => toggleFiles(fileKey)}
                      className="mt-1 text-xs text-blue-500 hover:text-blue-700"
                    >
                      {isExpanded
                        ? 'Ver menos'
                        : `+ ${commit.files_changed.length - FILES_PREVIEW} arquivo(s)`}
                    </button>
                  )}
                </div>
              );
            })()}
          </div>
        ))}
      </div>

      {remaining > 0 && (
        <button
          onClick={() => setVisibleCount((prev) => prev + pageSize)}
          className="mt-4 w-full py-2 text-sm text-blue-600 hover:text-blue-800 font-medium border border-blue-200 hover:border-blue-400 rounded-lg transition-colors"
        >
          Ver mais {Math.min(pageSize, remaining)} commits
        </button>
      )}
    </div>
  );
};

export default CommitLog;
