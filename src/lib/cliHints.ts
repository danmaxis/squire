import type { LockStatus } from './squireLock';
import type { Checkpoint, Project, Task } from './types';

/**
 * Comandos CLI de desobstrução sugeridos a partir do estado — mesma
 * heurística do `squire doctor` (checkpoint + lock + tasks), derivada dos
 * JSONs que a página já carrega. Os chips só copiam; não executam nada.
 */

export interface CliHint {
  cmd: string;
  why: string;
}

const IN_PROGRESS_STATUSES = new Set(['implementing', 'testing', 'homologating']);

/** Checkpoint aponta para uma task no meio do caminho e é retomável? */
export function isResumable(
  checkpoint: Checkpoint | null,
  project: Project,
  lock: LockStatus
): boolean {
  return Boolean(
    checkpoint &&
      checkpoint.cursor.current_task_id &&
      checkpoint.recovery.can_resume &&
      project.status !== 'completed' &&
      !lock.held
  );
}

export function projectCommands(args: {
  project: Project;
  tasks: Task[];
  lock: LockStatus;
  checkpoint: Checkpoint | null;
}): CliHint[] {
  const { project, tasks, lock, checkpoint } = args;
  const hints: CliHint[] = [];

  const runningHere = lock.held && lock.projectId === project.id;
  const runningElsewhere = lock.held && lock.projectId !== project.id;
  const hasPending = tasks.some((t) => t.status === 'pending');
  const hasBlocked = tasks.some((t) => t.status === 'blocked');

  if (runningHere) {
    hints.push({
      cmd: 'squire kill',
      why: 'encerra a sessão ativa deste projeto e libera o lock',
    });
  } else if (!runningElsewhere) {
    if (isResumable(checkpoint, project, lock)) {
      hints.push({
        cmd: `squire resume ${project.id}`,
        why: `retoma a sessão interrompida do checkpoint (parou em ${checkpoint!.cursor.current_task_id})`,
      });
    } else if (hasPending) {
      hints.push({
        cmd: `squire run ${project.id}`,
        why: 'executa as tasks pendentes em foreground',
      });
      hints.push({
        cmd: `squire bg ${project.id}`,
        why: 'executa em background (acompanhe com squire log)',
      });
    }
  }

  if (hasBlocked) {
    hints.push({
      cmd: `squire unblock ${project.id}`,
      why: 'todas as bloqueadas voltam para pending, mantendo o código',
    });
  }

  return hints.slice(0, 4);
}

export function taskCommands(
  projectId: string,
  task: Task,
  opts: { lockHeld: boolean; resumableTaskId: string | null }
): CliHint[] {
  if (task.status === 'blocked') {
    return [
      {
        cmd: `squire fix ${projectId} ${task.id}`,
        why: 'Claude implementa a correção, roda os testes e faz 1 homologação',
      },
      {
        cmd: `squire unblock ${projectId} ${task.id}`,
        why: 'volta para pending mantendo o código já escrito',
      },
      {
        cmd: `squire reset ${projectId} ${task.id}`,
        why: 'descarta o código não-commitado e recomeça do zero',
      },
    ];
  }

  if (
    IN_PROGRESS_STATUSES.has(task.status) &&
    !opts.lockHeld &&
    opts.resumableTaskId === task.id
  ) {
    return [
      {
        cmd: `squire resume ${projectId}`,
        why: 'a sessão morreu no meio desta task — retoma do checkpoint',
      },
    ];
  }

  return [];
}
