'use client';

import { useState } from 'react';
import { HistoryEvent } from '@/lib/types';

interface TimelineProps {
  events: HistoryEvent[];
  pageSize?: number;
}

const getActorColor = (actor: string) => {
  switch (actor) {
    case 'local_llm': return 'bg-blue-500';
    case 'claude_code': return 'bg-purple-500';
    case 'squire': return 'bg-gray-500';
    case 'human': return 'bg-green-500';
    default: return 'bg-gray-500';
  }
};

const getActorLabel = (actor: string) => {
  switch (actor) {
    case 'local_llm': return 'Local LLM';
    case 'claude_code': return 'Claude Code';
    case 'squire': return 'Squire';
    case 'human': return 'Human';
    default: return actor;
  }
};

const getIcon = (type: string) => {
  switch (type) {
    case 'tests_passed':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case 'tests_failed':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case 'homologation_approved':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      );
    case 'homologation_failed':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
        </svg>
      );
    case 'escalation_created':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      );
    case 'homologation_requested':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      );
    case 'task_completed':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case 'task_started':
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    default:
      return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" />
        </svg>
      );
  }
};

const getIconColor = (type: string) => {
  switch (type) {
    case 'tests_passed':
    case 'homologation_approved':
    case 'task_completed':
      return 'text-green-600';
    case 'tests_failed':
    case 'homologation_failed':
      return 'text-red-600';
    case 'escalation_created':
      return 'text-orange-600';
    default:
      return 'text-gray-600';
  }
};

interface SessionGroup {
  id: string;
  startedAt: string;
  endedAt: string | null;
  startKind: 'started' | 'resumed' | 'orphan';
  events: HistoryEvent[];
}

function groupBySession(events: HistoryEvent[]): SessionGroup[] {
  const asc = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const groups: SessionGroup[] = [];
  let current: SessionGroup | null = null;

  for (const e of asc) {
    if (e.type === 'session_started' || e.type === 'session_resumed') {
      current = {
        id: e.timestamp,
        startedAt: e.timestamp,
        endedAt: null,
        startKind: e.type === 'session_started' ? 'started' : 'resumed',
        events: [],
      };
      groups.push(current);
      continue;
    }
    if (e.type === 'session_ended') {
      if (current) {
        current.endedAt = e.timestamp;
      }
      continue;
    }
    if (!current) {
      // Events before any session marker (legacy logs)
      current = {
        id: `orphan-${e.timestamp}`,
        startedAt: e.timestamp,
        endedAt: null,
        startKind: 'orphan',
        events: [],
      };
      groups.push(current);
    }
    current.events.push(e);
  }

  // Newest first for display
  return groups.reverse().map((g) => ({
    ...g,
    events: g.events.sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    ),
  }));
}

function formatSessionLabel(g: SessionGroup): string {
  const start = new Date(g.startedAt);
  const shortId = g.id.slice(-8);
  const kindLabel =
    g.startKind === 'resumed'
      ? 'Sessão retomada'
      : g.startKind === 'orphan'
      ? 'Eventos sem sessão'
      : 'Sessão';
  return `${kindLabel} · ${start.toLocaleString('pt-BR')} · ${shortId}`;
}

function EventRow({ event }: { event: HistoryEvent }) {
  return (
    <div className="relative pl-6">
      <div
        className={`absolute -left-[21px] top-1 w-3 h-3 rounded-full border-2 border-white ${getActorColor(event.actor)}`}
      />
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={`p-1.5 rounded-md bg-opacity-10 ${getIconColor(event.type)} bg-opacity-20`}
            >
              {getIcon(event.type)}
            </span>
            <span className="text-sm font-semibold text-gray-800">
              {getActorLabel(event.actor)}
            </span>
            {event.attempt !== null && (
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                #{event.attempt}
              </span>
            )}
            <span className="text-xs text-gray-400">
              • {new Date(event.timestamp).toLocaleString('pt-BR')}
            </span>
          </div>
          <p className="text-sm text-gray-600 leading-relaxed line-clamp-4">
            {event.summary}
          </p>
        </div>
        <div className="text-xs text-gray-400 whitespace-nowrap mt-1 sm:mt-0">
          {event.type}
        </div>
      </div>
    </div>
  );
}

export function Timeline({ events, pageSize = 20 }: TimelineProps) {
  const groups = groupBySession(events);
  // Latest group expanded by default; older ones collapsed.
  const [openSessions, setOpenSessions] = useState<Set<string>>(
    () => new Set(groups.slice(0, 1).map((g) => g.id))
  );
  const [visibleCount, setVisibleCount] = useState(pageSize);

  const toggleSession = (id: string) => {
    const next = new Set(openSessions);
    next.has(id) ? next.delete(id) : next.add(id);
    setOpenSessions(next);
  };

  if (groups.length === 0) {
    return <p className="text-sm text-gray-400 italic">Nenhum evento registrado.</p>;
  }

  // Across all open sessions, count events for pagination
  let renderedCount = 0;
  const groupsToRender = groups.map((g) => {
    const isOpen = openSessions.has(g.id);
    if (!isOpen) return { group: g, events: [] as HistoryEvent[] };
    const remaining = Math.max(0, visibleCount - renderedCount);
    const slice = g.events.slice(0, remaining);
    renderedCount += slice.length;
    return { group: g, events: slice };
  });

  const totalEventsInOpen = groups
    .filter((g) => openSessions.has(g.id))
    .reduce((acc, g) => acc + g.events.length, 0);
  const moreAvailable = Math.max(0, totalEventsInOpen - visibleCount);

  return (
    <div className="space-y-4">
      {groupsToRender.map(({ group, events: visible }) => {
        const isOpen = openSessions.has(group.id);
        return (
          <div
            key={group.id}
            className="border border-gray-200 rounded-lg overflow-hidden"
          >
            <button
              onClick={() => toggleSession(group.id)}
              className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 text-left"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    group.endedAt ? 'bg-gray-400' : 'bg-green-500'
                  }`}
                  title={group.endedAt ? 'Sessão encerrada' : 'Sessão em andamento'}
                />
                <span className="text-xs font-medium text-gray-700 font-mono">
                  {formatSessionLabel(group)}
                </span>
                <span className="text-[11px] text-gray-500">
                  ({group.events.length} eventos)
                </span>
              </div>
              <span className="text-gray-400 text-sm">{isOpen ? '▾' : '▸'}</span>
            </button>

            {isOpen && (
              <div className="p-3">
                {visible.length === 0 ? (
                  <p className="text-xs text-gray-400 italic">Sem eventos.</p>
                ) : (
                  <div className="relative pl-4 border-l-2 border-gray-200 space-y-6">
                    {visible.map((event, index) => (
                      <EventRow key={`${event.timestamp}-${index}`} event={event} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {moreAvailable > 0 && (
        <button
          onClick={() => setVisibleCount((prev) => prev + pageSize)}
          className="w-full py-2 text-sm text-blue-600 hover:text-blue-800 font-medium border border-blue-200 hover:border-blue-400 rounded-lg transition-colors"
        >
          Ver mais {Math.min(pageSize, moreAvailable)} eventos
        </button>
      )}
    </div>
  );
}
