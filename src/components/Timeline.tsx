import { HistoryEvent } from '@/lib/types';

interface TimelineProps {
  events: HistoryEvent[];
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

export function Timeline({ events }: TimelineProps) {
  const sortedEvents = [...events].sort((a, b) => 
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  return (
    <div className="relative pl-4 border-l-2 border-gray-200 space-y-6">
      {sortedEvents.map((event, index) => (
        <div key={`${event.timestamp}-${index}`} className="relative pl-6">
          <div className={`absolute -left-[21px] top-1 w-3 h-3 rounded-full border-2 border-white ${getActorColor(event.actor)}`} />
          
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className={`p-1.5 rounded-md bg-opacity-10 ${getIconColor(event.type)} bg-opacity-20`}>
                  {getIcon(event.type)}
                </span>
                <span className="text-sm font-semibold text-gray-800">{getActorLabel(event.actor)}</span>
                {event.attempt !== null && (
                  <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">#{event.attempt}</span>
                )}
                <span className="text-xs text-gray-400">• {new Date(event.timestamp).toLocaleDateString('pt-BR')}</span>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">
                {event.summary}
              </p>
            </div>
            <div className="text-xs text-gray-400 whitespace-nowrap mt-1 sm:mt-0">
              {event.type}
            </div>
          </div>
        </div>
      ))}
      
      {sortedEvents.length === 0 && (
        <p className="text-sm text-gray-400 italic">Nenhum evento registrado.</p>
      )}
    </div>
  );
}
