import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RefreshIndicator } from './RefreshIndicator';

describe('RefreshIndicator', () => {
  it('exibe "--:--:--" quando lastRefresh é null', () => {
    render(
      <RefreshIndicator lastRefresh={null} isRefreshing={false} refreshInterval={30000} />
    );
    expect(screen.getByText('--:--:--')).toBeInTheDocument();
  });

  it('exibe horário formatado quando lastRefresh é uma Date', () => {
    // Data fixa para evitar dependência de fuso
    const date = new Date('2026-03-29T10:05:30Z');
    render(
      <RefreshIndicator lastRefresh={date} isRefreshing={false} refreshInterval={30000} />
    );
    // Verifica que o horário aparece (formato pt-BR HH:MM:SS)
    const timeText = screen.getByText(/\d{2}:\d{2}:\d{2}/);
    expect(timeText).toBeInTheDocument();
  });

  it('exibe "Atualizado" quando não está atualizando e sem erro', () => {
    render(
      <RefreshIndicator lastRefresh={null} isRefreshing={false} refreshInterval={30000} />
    );
    expect(screen.getByText('Atualizado')).toBeInTheDocument();
  });

  it('exibe "Atualizando..." quando isRefreshing é true', () => {
    render(
      <RefreshIndicator lastRefresh={null} isRefreshing={true} refreshInterval={30000} />
    );
    expect(screen.getByText('Atualizando...')).toBeInTheDocument();
  });

  it('exibe "Erro" quando isError é true', () => {
    render(
      <RefreshIndicator lastRefresh={null} isRefreshing={false} refreshInterval={30000} isError={true} />
    );
    expect(screen.getByText('Erro')).toBeInTheDocument();
  });

  it('exibe o intervalo em segundos', () => {
    render(
      <RefreshIndicator lastRefresh={null} isRefreshing={false} refreshInterval={30000} />
    );
    expect(screen.getByText('(30s)')).toBeInTheDocument();
  });
});
