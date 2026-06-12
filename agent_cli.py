#!/usr/bin/env python3
"""
Agente host do squire — executa comandos enfileirados pelo dashboard.
Invocado por 'squire agent [--once] [--poll N]'.

O dashboard (container, sem acesso ao host) escreve comandos em
$SQUIRE_STATE_ROOT/commands/pending/<uuid>.json. Este agente roda na VM,
reivindica cada comando via rename atômico para running/, executa o CLI
correspondente com argv em lista (nunca shell) e grava o resultado em
done/<uuid>.json. Apenas os tipos da whitelist CommandType são aceitos,
com validação estrita de project_id/args.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import checkpoint as ckpt
import config
from models import CommandResult, CommandStatus, CommandType, QueuedCommand

# ── Cores ──────────────────────────────────────────────────────────

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"

SQUIRE_DIR = Path(__file__).resolve().parent
WRAPPER = SQUIRE_DIR / "squire"
VENV_PY = SQUIRE_DIR / ".venv" / "bin" / "python"

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TAIL_BYTES = 8 * 1024


def _log(msg: str, kind: str = "info") -> None:
    icon = {"info": f"{CYAN}→{RESET}", "ok": f"{GREEN}✓{RESET}",
            "warn": f"{YELLOW}⚠{RESET}", "error": f"{RED}✗{RESET}"}[kind]
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {icon} {msg}", flush=True)


# ── Filesystem da fila ─────────────────────────────────────────────

def ensure_queue_dirs() -> None:
    for d in (config.COMMANDS_PENDING, config.COMMANDS_RUNNING, config.COMMANDS_DONE):
        d.mkdir(parents=True, exist_ok=True)


def recover_orphans() -> int:
    """Comandos órfãos em running/ (agente morreu no meio) viram failed.

    Nunca re-executa — um 'squire run' duplicado seria pior que pedir
    ao usuário para clicar de novo.
    """
    count = 0
    for path in sorted(config.COMMANDS_RUNNING.glob("*.json")):
        try:
            cmd = QueuedCommand.model_validate_json(path.read_text())
            result = CommandResult(
                id=cmd.id, type=cmd.type, project_id=cmd.project_id,
                status=CommandStatus.failed,
                error="agente reiniciado durante a execução — repita o comando",
                finished_at=datetime.now(timezone.utc),
            )
            ckpt.save_model(config.COMMANDS_DONE / path.name, result)
        except Exception:
            pass  # arquivo ilegível — só remove
        path.unlink(missing_ok=True)
        count += 1
    return count


def cleanup_done() -> int:
    """Apaga resultados em done/ mais velhos que o TTL."""
    cutoff = time.time() - config.COMMAND_RESULT_TTL_HOURS * 3600
    count = 0
    for path in config.COMMANDS_DONE.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                count += 1
        except FileNotFoundError:
            pass
    return count


def claim_next() -> Optional[Path]:
    """Reivindica o pending mais antigo movendo-o (atômico) para running/."""
    candidates = sorted(
        config.COMMANDS_PENDING.glob("*.json"), key=lambda p: p.stat().st_mtime
    )
    for path in candidates:
        target = config.COMMANDS_RUNNING / path.name
        try:
            os.rename(path, target)
            return target
        except FileNotFoundError:
            continue  # outro processo levou — segue
    return None


# ── Validação + montagem de argv ───────────────────────────────────

def validate(cmd: QueuedCommand) -> Optional[str]:
    """Retorna mensagem de erro, ou None se o comando é válido."""
    needs_project = cmd.type != CommandType.kill
    if needs_project:
        if not cmd.project_id or not _PROJECT_ID_RE.match(cmd.project_id):
            return f"project_id inválido: {cmd.project_id!r}"
        project_dir = (config.PROJECTS_DIR / cmd.project_id).resolve()
        if not str(project_dir).startswith(str(config.PROJECTS_DIR.resolve()) + os.sep):
            return f"project_id fora de projects/: {cmd.project_id!r}"
        exists = project_dir.exists()
        if cmd.type == CommandType.new_project:
            if exists:
                return f"projeto '{cmd.project_id}' já existe"
        elif not exists:
            return f"projeto '{cmd.project_id}' não existe"

    if cmd.type == CommandType.new_project:
        backend = cmd.args.get("backend", "opencode")
        if backend not in ("opencode", "litellm", "crush"):
            return f"backend inválido: {backend!r}"
        repo_path = cmd.args.get("repo_path")
        if repo_path is not None:
            rp = Path(repo_path)
            if not rp.is_absolute():
                return f"repo_path deve ser absoluto: {repo_path!r}"
            root = config.AGENT_REPO_ROOT.resolve()
            if not str(rp.resolve()).startswith(str(root) + os.sep):
                return f"repo_path fora de {root}: {repo_path!r}"

    if cmd.type == CommandType.plan_tasks:
        mode = cmd.args.get("mode", "append")
        if mode not in ("append", "replace"):
            return f"mode inválido: {mode!r}"

    if cmd.type in (CommandType.split_task, CommandType.fix_task):
        task_id = cmd.args.get("task_id", "")
        if not _TASK_ID_RE.match(task_id):
            return f"task_id inválido: {task_id!r}"

    return None


def build_argv(cmd: QueuedCommand) -> list[str]:
    """Monta o argv (lista, nunca shell) para o comando validado."""
    if cmd.type == CommandType.new_project:
        argv = [str(WRAPPER), "new", cmd.project_id, "--yes"]
        if cmd.args.get("name"):
            argv += ["--name", str(cmd.args["name"])]
        if cmd.args.get("repo_path"):
            argv += ["--repo", str(cmd.args["repo_path"])]
        if cmd.args.get("stack"):
            argv += ["--stack", str(cmd.args["stack"])]
        argv += ["--backend", str(cmd.args.get("backend", "opencode"))]
        if cmd.args.get("git_init", True):
            argv += ["--git-init"]
        return argv

    if cmd.type == CommandType.run:
        return [str(WRAPPER), "bg", cmd.project_id]

    if cmd.type == CommandType.resume:
        return [str(WRAPPER), "resume", cmd.project_id, "bg"]

    if cmd.type == CommandType.kill:
        return [str(WRAPPER), "kill"]

    if cmd.type == CommandType.plan_tasks:
        argv = [str(VENV_PY), "-u", str(SQUIRE_DIR / "tasks_cli.py"),
                "plan", cmd.project_id, "--yes",
                "--mode", str(cmd.args.get("mode", "append"))]
        if cmd.args.get("description"):
            argv += ["--desc", str(cmd.args["description"])]
        return argv

    if cmd.type == CommandType.split_task:
        return [str(VENV_PY), "-u", str(SQUIRE_DIR / "tasks_cli.py"),
                "split", cmd.project_id, str(cmd.args["task_id"]), "--yes"]

    if cmd.type == CommandType.fix_task:
        return [str(VENV_PY), "-u", str(SQUIRE_DIR / "fix_cli.py"),
                cmd.project_id, str(cmd.args["task_id"]), "--yes"]

    raise ValueError(f"tipo não suportado: {cmd.type}")


# ── Execução ───────────────────────────────────────────────────────

def _tail(text: str) -> str:
    return text[-_TAIL_BYTES:] if text else ""


def execute(running_path: Path) -> CommandResult:
    """Executa o comando reivindicado e grava o resultado em done/."""
    started = datetime.now(timezone.utc)
    try:
        cmd = QueuedCommand.model_validate_json(running_path.read_text())
    except Exception as e:
        result = CommandResult(
            id=running_path.stem, type=CommandType.kill, status=CommandStatus.failed,
            error=f"JSON de comando inválido: {e}",
            started_at=started, finished_at=datetime.now(timezone.utc),
        )
        ckpt.save_model(config.COMMANDS_DONE / running_path.name, result)
        running_path.unlink(missing_ok=True)
        return result

    problem = validate(cmd)
    if problem is None:
        argv = build_argv(cmd)
        _log(f"executando {cmd.type.value} ({cmd.project_id or '-'}): {' '.join(argv[:4])}…")
        env = {**os.environ, "SQUIRE_STATE_ROOT": str(config.STATE_ROOT)}
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True,
                timeout=config.COMMAND_TIMEOUT_SECONDS, env=env,
            )
            status = CommandStatus.done if proc.returncode == 0 else CommandStatus.failed
            result = CommandResult(
                id=cmd.id, type=cmd.type, project_id=cmd.project_id,
                status=status, exit_code=proc.returncode,
                stdout_tail=_tail(proc.stdout), stderr_tail=_tail(proc.stderr),
                started_at=started, finished_at=datetime.now(timezone.utc),
                error=None if status == CommandStatus.done else f"exit code {proc.returncode}",
            )
        except subprocess.TimeoutExpired:
            result = CommandResult(
                id=cmd.id, type=cmd.type, project_id=cmd.project_id,
                status=CommandStatus.failed,
                error=f"timeout após {config.COMMAND_TIMEOUT_SECONDS}s",
                started_at=started, finished_at=datetime.now(timezone.utc),
            )
    else:
        _log(f"comando rejeitado: {problem}", "warn")
        result = CommandResult(
            id=cmd.id, type=cmd.type, project_id=cmd.project_id,
            status=CommandStatus.failed, error=problem,
            started_at=started, finished_at=datetime.now(timezone.utc),
        )

    ckpt.save_model(config.COMMANDS_DONE / running_path.name, result)
    running_path.unlink(missing_ok=True)
    kind = "ok" if result.status == CommandStatus.done else "error"
    _log(f"{cmd.type.value} → {result.status.value}", kind)
    return result


# ── Pidfile (instância única) ──────────────────────────────────────

def _acquire_pidfile() -> bool:
    pidfile = config.COMMANDS_DIR / "agent.pid"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            _log(f"outro agente já roda (pid {pid})", "error")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass  # stale
    pidfile.write_text(str(os.getpid()))
    return True


def _release_pidfile() -> None:
    pidfile = config.COMMANDS_DIR / "agent.pid"
    try:
        if pidfile.exists() and int(pidfile.read_text().strip()) == os.getpid():
            pidfile.unlink()
    except (ValueError, OSError):
        pass


# ── Main loop ──────────────────────────────────────────────────────

def run_agent(once: bool = False, poll_seconds: Optional[float] = None) -> int:
    poll = poll_seconds if poll_seconds is not None else config.AGENT_POLL_SECONDS
    ensure_queue_dirs()
    if not _acquire_pidfile():
        return 1

    try:
        orphans = recover_orphans()
        if orphans:
            _log(f"{orphans} comando(s) órfão(s) marcados como failed", "warn")
        cleanup_done()
        _log(f"agente ativo — fila em {config.COMMANDS_DIR} (poll {poll}s)")

        last_cleanup = time.time()
        while True:
            claimed = claim_next()
            if claimed is not None:
                execute(claimed)
                continue  # drena a fila antes de dormir
            if once:
                return 0
            time.sleep(poll)
            if time.time() - last_cleanup > 600:
                cleanup_done()
                last_cleanup = time.time()
    except KeyboardInterrupt:
        _log("agente encerrado (Ctrl+C)")
        return 0
    finally:
        _release_pidfile()


def main() -> None:
    sys.path.insert(0, str(SQUIRE_DIR))
    args = sys.argv[1:]
    if any(a in ("-h", "--help", "help") for a in args):
        print(f"""
{BOLD}squire agent{RESET} — executa comandos enfileirados pelo dashboard

  {CYAN}squire agent{RESET}             Loop contínuo (use com systemd --user)
  {CYAN}squire agent --once{RESET}      Processa a fila e sai (testes/cron)
  {CYAN}squire agent --poll N{RESET}    Intervalo de polling em segundos

Fila: $SQUIRE_STATE_ROOT/commands/{{pending,running,done}}/
Tipos aceitos: new_project, run, resume, kill, plan_tasks, split_task, fix_task
""")
        return
    once = "--once" in args
    poll = None
    if "--poll" in args:
        try:
            poll = float(args[args.index("--poll") + 1])
        except (IndexError, ValueError):
            print(f"{RED}✗{RESET} --poll requer um número de segundos", file=sys.stderr)
            sys.exit(1)
    sys.exit(run_agent(once=once, poll_seconds=poll))


if __name__ == "__main__":
    main()
