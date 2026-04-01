import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import CommitLog from './CommitLog';
import type { CommitSummary } from '@/lib/types';

const makeCommit = (overrides?: Partial<CommitSummary>): CommitSummary => ({
  sha: 'abc1234def56789',
  message: 'feat: commit de teste',
  timestamp: '2026-03-29T10:00:00Z',
  diff_summary: 'Resumo do diff',
  files_changed: ['src/app/page.tsx'],
  ...overrides,
});

const makeCommits = (count: number): CommitSummary[] =>
  Array.from({ length: count }, (_, i) =>
    makeCommit({ sha: `sha${i}`, message: `Commit ${i + 1}` })
  );

describe('CommitLog', () => {
  it('renderiza estado vazio quando não há commits', () => {
    render(<CommitLog commits={[]} />);
    expect(screen.getByText('Nenhum commit encontrado')).toBeInTheDocument();
  });

  it('renderiza estado de loading quando isLoading=true', () => {
    render(<CommitLog commits={[]} isLoading={true} />);
    expect(screen.getByText(/carregando histórico/i)).toBeInTheDocument();
  });

  it('renderiza todos os commits quando total ≤ pageSize', () => {
    render(<CommitLog commits={makeCommits(5)} pageSize={20} />);
    expect(screen.getByText('Commit 1')).toBeInTheDocument();
    expect(screen.getByText('Commit 5')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /ver mais/i })).not.toBeInTheDocument();
  });

  it('renderiza apenas pageSize commits quando total > pageSize', () => {
    render(<CommitLog commits={makeCommits(25)} pageSize={20} />);
    for (let i = 1; i <= 20; i++) {
      expect(screen.getByText(`Commit ${i}`)).toBeInTheDocument();
    }
    expect(screen.queryByText('Commit 21')).not.toBeInTheDocument();
  });

  it('exibe botão "Ver mais N commits" quando há mais que pageSize', () => {
    render(<CommitLog commits={makeCommits(25)} pageSize={20} />);
    expect(screen.getByRole('button', { name: /ver mais 5 commits/i })).toBeInTheDocument();
  });

  it('botão "Ver mais" expande lista em pageSize', () => {
    render(<CommitLog commits={makeCommits(25)} pageSize={20} />);
    expect(screen.queryByText('Commit 21')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /ver mais/i }));

    expect(screen.getByText('Commit 21')).toBeInTheDocument();
    expect(screen.getByText('Commit 25')).toBeInTheDocument();
  });

  it('botão desaparece quando todos os commits estão visíveis', () => {
    render(<CommitLog commits={makeCommits(25)} pageSize={20} />);
    fireEvent.click(screen.getByRole('button', { name: /ver mais/i }));
    expect(screen.queryByRole('button', { name: /ver mais/i })).not.toBeInTheDocument();
  });

  it('não renderiza heading interno duplicado', () => {
    render(<CommitLog commits={makeCommits(1)} />);
    expect(screen.queryByText('Histórico de Commits')).not.toBeInTheDocument();
  });

  it('usa pageSize=20 como default', () => {
    render(<CommitLog commits={makeCommits(21)} />);
    expect(screen.getByRole('button', { name: /ver mais 1 commits/i })).toBeInTheDocument();
  });

  it('exibe sha truncado e diff_summary', () => {
    render(<CommitLog commits={[makeCommit({ sha: 'abcdef1234567', diff_summary: 'Resumo visível' })]} />);
    expect(screen.getByText('abcdef1')).toBeInTheDocument();
    expect(screen.getByText('Resumo visível')).toBeInTheDocument();
  });

  it('não exibe botão de expandir quando arquivos ≤ 3', () => {
    const commit = makeCommit({ files_changed: ['a.ts', 'b.ts', 'c.ts'] });
    render(<CommitLog commits={[commit]} />);
    expect(screen.queryByRole('button', { name: /arquivo/i })).not.toBeInTheDocument();
  });

  it('exibe apenas 3 arquivos e botão "+ N arquivo(s)" quando arquivos > 3', () => {
    const files = ['a.ts', 'b.ts', 'c.ts', 'd.ts', 'e.ts'];
    const commit = makeCommit({ files_changed: files });
    render(<CommitLog commits={[commit]} />);

    expect(screen.getByText('a.ts')).toBeInTheDocument();
    expect(screen.getByText('c.ts')).toBeInTheDocument();
    expect(screen.queryByText('d.ts')).not.toBeInTheDocument();
    expect(screen.getByText('+ 2 arquivo(s)')).toBeInTheDocument();
  });

  it('expande lista de arquivos ao clicar no botão', () => {
    const files = ['a.ts', 'b.ts', 'c.ts', 'd.ts', 'e.ts'];
    render(<CommitLog commits={[makeCommit({ files_changed: files })]} />);

    fireEvent.click(screen.getByText('+ 2 arquivo(s)'));

    expect(screen.getByText('d.ts')).toBeInTheDocument();
    expect(screen.getByText('e.ts')).toBeInTheDocument();
    expect(screen.getByText('Ver menos')).toBeInTheDocument();
  });

  it('colapsa lista de arquivos ao clicar "Ver menos"', () => {
    const files = ['a.ts', 'b.ts', 'c.ts', 'd.ts'];
    render(<CommitLog commits={[makeCommit({ files_changed: files })]} />);

    fireEvent.click(screen.getByText('+ 1 arquivo(s)'));
    expect(screen.getByText('d.ts')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Ver menos'));
    expect(screen.queryByText('d.ts')).not.toBeInTheDocument();
  });
});
