import { randomUUID } from 'crypto';
import { promises as fs } from 'fs';
import { join } from 'path';
import { readJson, writeJsonAtomic } from './atomic';
import { DATA_PATH } from './squireStatePath';
import type { CommandResult, CommandStatus, CommandType, QueuedCommand } from './types';

/**
 * Fila de comandos para o agente host (squire agent).
 * Protocolo: pending/<uuid>.json → o agente move para running/ → resultado
 * em done/<uuid>.json. O dashboard só escreve em pending/ e lê os três.
 */

export const commandsDir = () => join(DATA_PATH, 'commands');
const pendingDir = () => join(commandsDir(), 'pending');
const runningDir = () => join(commandsDir(), 'running');
const doneDir = () => join(commandsDir(), 'done');

export async function enqueueCommand(
  type: CommandType,
  projectId: string | null,
  args: Record<string, unknown> = {}
): Promise<QueuedCommand> {
  const cmd: QueuedCommand = {
    id: randomUUID(),
    type,
    project_id: projectId,
    args,
    created_at: new Date().toISOString(),
    requested_by: 'dashboard',
  };
  await fs.mkdir(pendingDir(), { recursive: true });
  await writeJsonAtomic(join(pendingDir(), `${cmd.id}.json`), cmd);
  return cmd;
}

export interface CommandStatusView {
  status: CommandStatus;
  command: QueuedCommand | null;
  result: CommandResult | null;
}

export async function getCommandStatus(
  id: string
): Promise<CommandStatusView | null> {
  const result = await readJson<CommandResult>(join(doneDir(), `${id}.json`));
  if (result) {
    return { status: result.status, command: null, result };
  }
  const running = await readJson<QueuedCommand>(join(runningDir(), `${id}.json`));
  if (running) {
    return { status: 'running', command: running, result: null };
  }
  const pending = await readJson<QueuedCommand>(join(pendingDir(), `${id}.json`));
  if (pending) {
    return { status: 'pending', command: pending, result: null };
  }
  return null;
}
