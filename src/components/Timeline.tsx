'use client';

interface TimelineEvent {
  id: string;
  type: 'DEPLOY' | 'BUG' | 'FEATURE' | 'MEETING' | 'OTHER';
  actor: string;
  date: string;
  message: string;
}

interface TimelineProps {
  events: TimelineEvent[];
}

const getIcon = (type: string) => {
  switch (type) {
    case 'DEPLOY': return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
      </svg>
    );
    case 'BUG': return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    );
    case 'FEATURE': return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    );
    case 'MEETING': return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    );
    default: return (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );
  }
};

const getActorColor = (actor: string) => {
  // Gera uma cor consistente baseada no nome do ator
  const colors = [
    'bg-blue-500', 'bg-green-500', 'bg-purple-500', 'bg-orange-500', 
    'bg-pink-500', 'bg-indigo-500', 'bg-teal-500', 'bg-red-500'
  ];
  let hash = 0;
  for (let i = 0; i < actor.length; i++) {
    hash = actor.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % colors.length;
  return colors[index];
};

export default function Timeline({ events }: TimelineProps) {
  // Ordenar eventos por data (mais recente primeiro)
  const sortedEvents = [...events].sort((a, b) => 
    new Date(b.date).getTime() - new Date(a.date).getTime()
  );

  return (
    <div className="relative pl-4 border-l-2 border-gray-200 space-y-6">
      {sortedEvents.map((event, index) => (
        <div key={event.id} className="relative pl-6">
          {/* Dot no timeline */}
          <div className={`absolute -left-[21px] top-1 w-3 h-3 rounded-full border-2 border-white ${getActorColor(event.actor)}`} />
          
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className={`p-1.5 rounded-md text-white ${getActorColor(event.actor)} bg-opacity-10`}>
                  {getIcon(event.type)}
                </span>
                <span className="text-sm font-semibold text-gray-800">{event.actor}</span>
                <span className="text-xs text-gray-400">• {new Date(event.date).toLocaleDateString('pt-BR')}</span>
              </div>
              <p className="text-sm text-gray-600 leading-relaxed">
                {event.message}
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