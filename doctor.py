#!/usr/bin/env python3
"""
Health check do ambiente do squire.
Invocado por 'squire doctor [--fix]'.

Verifica tudo que precisa estar de pé para uma sessão rodar: estado,
endpoint do LLM, binários, locks e sanidade por projeto. Sai com código 1
se houver qualquer FAIL. '--fix' aplica apenas limpezas seguras (locks
comprovadamente mortos/livres).
"""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

import checkpoint as ckpt
import config
from models import SessionLock, TaskStatus

# ── Cores / formatação ─────────────────────────────────────────────

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

OK = "ok"
WARN = "warn"
FAIL = "fail"
INFO = "info"

_BADGE = {
    OK: f"{GREEN}[ OK ]{RESET}",
    WARN: f"{YELLOW}[WARN]{RESET}",
    FAIL: f"{RED}[FAIL]{RESET}",
    INFO: f"{CYAN}[INFO]{RESET}",
}


@dataclass
class CheckResult:
    status: str  # ok | warn | fail | info
    name: str
    detail: str = ""

    def render(self) -> str:
        detail = f"  {DIM}{self.detail}{RESET}" if self.detail else ""
        return f"{_BADGE[self.status]} {self.name}{detail}"


# ── Checks ─────────────────────────────────────────────────────────

def check_state_root() -> list[CheckResult]:
    root = config.STATE_ROOT
    if not root.exists():
        return [CheckResult(FAIL, "state root", f"{root} não existe")]
    if not os.access(root, os.W_OK):
        return [CheckResult(FAIL, "state root", f"{root} sem permissão de escrita")]
    results = [CheckResult(OK, "state root", str(root))]
    if not config.PROJECTS_DIR.exists():
        results.append(CheckResult(WARN, "projects/", "diretório ausente — 'squire new' cria"))
    return results


def check_llm_endpoint() -> list[CheckResult]:
    url = f"{config.LITELLM_BASE_URL.rstrip('/')}/models"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {config.LITELLM_API_KEY}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return [CheckResult(
            FAIL, "LLM endpoint",
            f"{config.LITELLM_BASE_URL} inacessível ({type(exc).__name__}) — inner loop não funciona",
        )]

    results = [CheckResult(OK, "LLM endpoint", config.LITELLM_BASE_URL)]
    available = {m.get("id", "") for m in data.get("data", [])}
    wanted = {config.LITELLM_MODEL, config.MODEL_LOW, config.MODEL_MEDIUM, config.MODEL_HIGH}
    for model in sorted(wanted):
        if model in available:
            results.append(CheckResult(OK, f"modelo '{model}'", "disponível"))
        else:
            results.append(CheckResult(
                WARN, f"modelo '{model}'",
                f"não listado pelo endpoint (disponíveis: {', '.join(sorted(available)) or 'nenhum'})",
            ))
    return results


def check_claude_bin() -> list[CheckResult]:
    path = shutil.which(config.CLAUDE_CODE_BIN)
    if not path:
        return [CheckResult(
            FAIL, "claude binary",
            f"'{config.CLAUDE_CODE_BIN}' não encontrado no PATH — homologação/escalação não funcionam",
        )]
    try:
        proc = subprocess.run(
            [config.CLAUDE_CODE_BIN, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        version = proc.stdout.strip() or proc.stderr.strip()
    except Exception as exc:
        return [CheckResult(WARN, "claude binary", f"{path} (--version falhou: {exc})")]
    return [CheckResult(OK, "claude binary", f"{path} ({version})")]


def _backends_in_use() -> set[str]:
    backends = {config.CODING_BACKEND}
    if config.PROJECTS_DIR.exists():
        for pdir in sorted(config.PROJECTS_DIR.iterdir()):
            project = ckpt.load_project(pdir.name)
            if project is not None and getattr(project, "coding_backend", None):
                backends.add(project.coding_backend)
    return backends


def check_backend_bins() -> list[CheckResult]:
    results = []
    in_use = _backends_in_use()
    bins = {"opencode": config.OPENCODE_BIN, "crush": config.CRUSH_BIN}
    for backend in sorted(in_use):
        if backend == "litellm":
            continue  # coberto pelo check do endpoint
        binary = bins.get(backend)
        if binary is None:
            results.append(CheckResult(WARN, f"backend '{backend}'", "desconhecido"))
            continue
        path = shutil.which(binary)
        if path:
            results.append(CheckResult(OK, f"backend '{backend}'", path))
        else:
            results.append(CheckResult(
                FAIL, f"backend '{backend}'",
                f"binário '{binary}' não encontrado no PATH (usado por projeto(s) configurado(s))",
            ))
    return results


def check_session_lock(fix: bool = False) -> list[CheckResult]:
    lock_file = config.SESSION_LOCK_FILE
    if not lock_file.exists():
        return [CheckResult(OK, "session.lock", "livre")]
    lock = ckpt.load_model(lock_file, SessionLock)
    if lock is None:
        if fix:
            lock_file.unlink()
            return [CheckResult(OK, "session.lock", "corrompido — removido (--fix)")]
        return [CheckResult(WARN, "session.lock", "corrompido — 'squire unlock' ou doctor --fix")]

    pid_alive = False
    if lock.pid:
        try:
            os.kill(lock.pid, 0)
            pid_alive = True
        except (ProcessLookupError, PermissionError):
            pid_alive = False

    expires = lock.acquired_at + timedelta(minutes=lock.ttl_minutes)
    expired = datetime.now(timezone.utc) > expires

    if pid_alive and not expired:
        return [CheckResult(
            WARN, "session.lock",
            f"sessão ativa: {lock.holder} (pid {lock.pid}, projeto {lock.project_id})",
        )]
    if pid_alive:
        return [CheckResult(WARN, "session.lock", f"TTL expirado mas pid {lock.pid} vivo — 'squire kill'")]
    if fix:
        lock_file.unlink()
        return [CheckResult(OK, "session.lock", f"stale (pid {lock.pid} morto) — removido (--fix)")]
    return [CheckResult(
        WARN, "session.lock",
        f"stale: pid {lock.pid} morto — 'squire unlock' ou doctor --fix",
    )]


def check_llm_lock(fix: bool = False) -> list[CheckResult]:
    lock_path = Path(config.STATE_ROOT) / "llm.lock"
    if not lock_path.exists():
        return [CheckResult(OK, "llm.lock", "livre")]
    try:
        with open(lock_path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
    except BlockingIOError:
        return [CheckResult(WARN, "llm.lock", "em uso por um processo ativo (chamada ao LLM em andamento)")]
    except OSError as exc:
        return [CheckResult(WARN, "llm.lock", f"não foi possível testar ({exc})")]
    if fix:
        lock_path.unlink()
        return [CheckResult(OK, "llm.lock", "livre — arquivo removido (--fix)")]
    # Arquivo presente mas flock livre = inofensivo (o lock é o flock, não o arquivo)
    return [CheckResult(OK, "llm.lock", "livre (arquivo residual é inofensivo)")]


def check_projects() -> list[CheckResult]:
    results = []
    if not config.PROJECTS_DIR.exists():
        return results
    for pdir in sorted(config.PROJECTS_DIR.iterdir()):
        if not pdir.is_dir():
            continue
        pid = pdir.name
        project = ckpt.load_project(pid)
        if project is None:
            results.append(CheckResult(WARN, f"projeto {pid}", "project.json ausente/inválido"))
            continue

        repo = Path(project.repo_path) if project.repo_path else None
        if repo is None or not repo.exists():
            results.append(CheckResult(WARN, f"projeto {pid}", f"repo_path não existe: {repo}"))
            continue

        details = []
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            results.append(CheckResult(WARN, f"projeto {pid}", f"{repo} não é repositório git"))
            continue
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout.strip()
        if dirty:
            details.append(f"working tree sujo ({len(dirty.splitlines())} arquivo(s))")

        try:
            tasks = ckpt.load_tasks(pid)
        except Exception:
            results.append(CheckResult(WARN, f"projeto {pid}", "tasks.json inválido"))
            continue
        blocked = sum(1 for t in tasks.tasks if t.status == TaskStatus.blocked)
        if blocked:
            details.append(f"{blocked} task(s) bloqueada(s) — 'squire unblock {pid}'")

        checkpoint = ckpt.load_checkpoint(pid)
        if (
            checkpoint is not None
            and checkpoint.cursor.current_task_id
            and project.status not in ("completed",)
        ):
            session_lock = ckpt.load_model(config.SESSION_LOCK_FILE, SessionLock)
            session_alive = (
                session_lock is not None and session_lock.holder == checkpoint.session_id
            )
            if not session_alive:
                age = datetime.now(timezone.utc) - checkpoint.last_heartbeat
                if age > timedelta(hours=1) and checkpoint.recovery.can_resume:
                    details.append(
                        f"sessão morta em {checkpoint.cursor.current_task_id} — retomável: 'squire resume {pid}'"
                    )

        if details:
            results.append(CheckResult(INFO, f"projeto {pid}", "; ".join(details)))
        else:
            status = getattr(project.status, "value", project.status)
            results.append(CheckResult(OK, f"projeto {pid}", status))
    return results


def check_alerts() -> list[CheckResult]:
    alerts = ckpt.load_alerts()
    pending = [a for a in alerts.alerts if not a.acknowledged]
    if not pending:
        return [CheckResult(OK, "alertas", "nenhum pendente")]
    critical = sum(1 for a in pending if a.severity.value == "critical")
    return [CheckResult(
        WARN, "alertas",
        f"{len(pending)} pendente(s) ({critical} critical) — 'squire alerts list'",
    )]


def check_stats_freshness() -> list[CheckResult]:
    if not config.STATS_FILE.exists():
        return [CheckResult(INFO, "global-stats", "ainda não criado (primeira execução cria)")]
    stats = ckpt.load_stats()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if stats.date == today and (stats.daily_claude_code_calls or stats.daily_local_llm_calls):
        return [CheckResult(OK, "global-stats", f"atividade hoje: {stats.daily_claude_code_calls} CC / {stats.daily_local_llm_calls} local")]
    return [CheckResult(INFO, "global-stats", "sem atividade hoje (contadores resetam por dia — esperado)")]


# ── Main ───────────────────────────────────────────────────────────

def run_doctor(fix: bool = False) -> int:
    print(f"{BOLD}squire doctor{RESET}\n")
    sections: list[tuple[str, list[CheckResult]]] = [
        ("Estado", check_state_root()),
        ("LLM local", check_llm_endpoint()),
        ("Claude Code", check_claude_bin()),
        ("Backends", check_backend_bins()),
        ("Locks", check_session_lock(fix) + check_llm_lock(fix)),
        ("Projetos", check_projects()),
        ("Alertas", check_alerts()),
        ("Stats", check_stats_freshness()),
    ]

    counts = {OK: 0, WARN: 0, FAIL: 0, INFO: 0}
    for title, results in sections:
        if not results:
            continue
        print(f"{BOLD}{title}{RESET}")
        for r in results:
            counts[r.status] += 1
            print(f"  {r.render()}")
        print()

    summary = (
        f"{GREEN}{counts[OK]} ok{RESET} · "
        f"{YELLOW}{counts[WARN]} warn{RESET} · "
        f"{RED}{counts[FAIL]} fail{RESET}"
    )
    print(summary)
    if counts[FAIL]:
        return 1
    return 0


def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent))
    fix = "--fix" in sys.argv[1:]
    if any(a in ("-h", "--help", "help") for a in sys.argv[1:]):
        print(f"""
{BOLD}squire doctor{RESET} — health check do ambiente

  {CYAN}squire doctor{RESET}          Roda todos os checks (exit 1 se houver FAIL)
  {CYAN}squire doctor --fix{RESET}    Também remove locks comprovadamente mortos/livres
""")
        return
    sys.exit(run_doctor(fix=fix))


if __name__ == "__main__":
    main()
