import React from 'react';

// Definindo tipos para os alertas baseados no contexto da aplicação
interface Alert {
  id: string;
  severity: 'critical' | 'warning';
  project: string;
  task: string;
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

// Interface para o props do componente
interface AlertBannerProps {
  alerts: Alert[];
}

const AlertBanner: React.FC<AlertBannerProps> = ({ alerts }) => {
  // Filtra apenas os alertas não acked
  const activeAlerts = alerts.filter((alert) => !alert.acknowledged);

  // Se não houver alertas ativos, não renderiza nada
  if (activeAlerts.length === 0) {
    return null;
  }

  // Estilos baseados na severidade
  const getBannerStyle = (severity: string) => {
    if (severity === 'critical') {
      return {
        backgroundColor: '#ef4444', // Vermelho (red-500)
        color: '#ffffff',
        borderColor: '#b91c1c',
      };
    }
    // Default para warning
    return {
      backgroundColor: '#f59e0b', // Amarelo (amber-500)
      color: '#1f2937', // Texto escuro para contraste
      borderColor: '#d97706',
    };
  };

  const getIcon = (severity: string) => {
    if (severity === 'critical') {
      return (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-5 w-5 mr-2 flex-shrink-0"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
            clipRule="evenodd"
          />
        </svg>
      );
    }
    // Warning Icon
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-5 w-5 mr-2 flex-shrink-0"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path
          fillRule="evenodd"
          d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
          clipRule="evenodd"
        />
      </svg>
    );
  };

  return (
    <div className="fixed top-0 left-0 right-0 z-50 overflow-y-auto shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="space-y-3">
          {activeAlerts.map((alert) => {
            const style = getBannerStyle(alert.severity);
            return (
              <div
                key={alert.id}
                className="flex items-start p-4 rounded-lg border-l-4 shadow-sm"
                style={{
                  ...style,
                  borderColor: style.borderColor,
                }}
              >
                <div className="flex-shrink-0 mt-0.5">
                  {getIcon(alert.severity)}
                </div>
                <div className="ml-3 flex-1">
                  <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-1">
                    <div className="font-semibold text-sm sm:text-base">
                      {alert.project} - {alert.task}
                    </div>
                    <div className="text-xs opacity-90 whitespace-nowrap mt-1 sm:mt-0">
                      {new Date(alert.timestamp).toLocaleString()}
                    </div>
                  </div>
                  <p className="mt-1 text-sm opacity-95">{alert.message}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default AlertBanner;