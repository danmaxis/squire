import { describe, it, expect } from 'vitest';
import {
  CURSOR_STEP_LABELS,
  PROJECT_STATUS_LABELS,
  TASK_STATUS_LABELS,
} from './statusMaps';

describe('statusMaps', () => {
  it('todos os labels são PT não-vazios (nada de enum cru ou inglês)', () => {
    const all = {
      ...PROJECT_STATUS_LABELS,
      ...TASK_STATUS_LABELS,
      ...CURSOR_STEP_LABELS,
    };
    for (const [key, label] of Object.entries(all)) {
      expect(label, key).toBeTruthy();
      expect(label, key).not.toBe(key); // não pode ser o enum cru
    }
    // sentinelas contra regressão de idioma
    expect(PROJECT_STATUS_LABELS.blocked).toBe('Bloqueado');
    expect(TASK_STATUS_LABELS.pending).toBe('pendente');
    expect(CURSOR_STEP_LABELS.llm_execution).toBe('execução LLM');
  });
});
