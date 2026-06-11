#!/usr/bin/env python3
"""
CLI para gerenciamento de alertas do squire.
Invocado por 'squire alerts <subcmd> [args]'.

Os índices exibidos por 'alerts list' referem-se à posição do alerta na
lista de NÃO-reconhecidos (ordem do arquivo), e são o que 'ack'/'rm'
aceitam. O dashboard é um segundo escritor de alerts.json — em ambientes
com o dashboard ativo, prefira os seletores --project/--task, que não
sofrem corrida de índice.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import checkpoint as ckpt
import config
from models import Alert, AlertList, AlertSeverity

# ── Cores ──────────────────────────────────────────────────────────

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


SEVERITY_LABEL = {
    AlertSeverity.critical: _c(RED, "CRIT"),
    AlertSeverity.warning: _c(YELLOW, "WARN"),
}


# ── Helpers ────────────────────────────────────────────────────────

def _age(created_at: datetime) -> str:
    """Idade compacta: 12min, 5h, 3d."""
    now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = now - created_at
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{delta.days}d"


def _indexed_unacked(alerts: AlertList) -> list[tuple[int, Alert]]:
    """Pares (índice 1-based, alerta) dos não-reconhecidos, na ordem do arquivo."""
    return [
        (i, a)
        for i, a in enumerate(
            (a for a in alerts.alerts if not a.acknowledged), start=1
        )
    ]


def _format_line(idx: Optional[int], alert: Alert, dim: bool = False) -> str:
    idx_str = f"{idx:3}" if idx is not None else "  —"
    task = alert.task_id or "—"
    msg = alert.message.replace("\n", " ")
    if len(msg) > 70:
        msg = msg[:67] + "..."
    line = (
        f"{idx_str}  {SEVERITY_LABEL[alert.severity]}  "
        f"{alert.project_id}/{task}  {_c(DIM, _age(alert.created_at))}  "
        f"{alert.type}: {msg}"
    )
    if dim:
        return f"{DIM}{line}{RESET}"
    return line


def _resolve_indexes(alerts: AlertList, raw: list[str]) -> list[Alert]:
    """Resolve índices 1-based contra a lista de não-reconhecidos."""
    indexed = dict(_indexed_unacked(alerts))
    selected: list[Alert] = []
    for token in raw:
        try:
            idx = int(token)
        except ValueError:
            print(f"{RED}✗{RESET} Índice inválido: '{token}'", file=sys.stderr)
            sys.exit(1)
        if idx not in indexed:
            print(
                f"{RED}✗{RESET} Índice {idx} fora do alcance "
                f"(há {len(indexed)} alertas não-reconhecidos — veja 'squire alerts list').",
                file=sys.stderr,
            )
            sys.exit(1)
        selected.append(indexed[idx])
    return selected


def _save(alerts: AlertList) -> None:
    ckpt.save_model(config.ALERTS_FILE, alerts)


# ── Comandos ───────────────────────────────────────────────────────

def cmd_list(show_all: bool = False, project: Optional[str] = None) -> None:
    alerts = ckpt.load_alerts()
    indexed = _indexed_unacked(alerts)

    visible = [
        (idx, a) for idx, a in indexed
        if project is None or a.project_id == project
    ]
    acked = [
        a for a in alerts.alerts
        if a.acknowledged and (project is None or a.project_id == project)
    ]

    if not visible and not (show_all and acked):
        scope = f" do projeto '{project}'" if project else ""
        print(f"{GREEN}✓{RESET} Nenhum alerta pendente{scope}.")
        return

    if visible:
        print(f"{BOLD}Alertas pendentes ({len(visible)}):{RESET}")
        for idx, alert in visible:
            print(_format_line(idx, alert))
    if show_all and acked:
        print(f"\n{BOLD}Reconhecidos ({len(acked)}):{RESET}")
        for alert in acked:
            print(_format_line(None, alert, dim=True))
    if visible:
        print(f"\n{DIM}Use 'squire alerts ack <n>' ou 'squire alerts ack --all'.{RESET}")


def cmd_ack(
    indexes: list[str],
    ack_all: bool = False,
    project: Optional[str] = None,
    task: Optional[str] = None,
) -> None:
    alerts = ckpt.load_alerts()

    if indexes:
        targets = _resolve_indexes(alerts, indexes)
    elif ack_all or project or task:
        targets = [
            a for a in alerts.alerts
            if not a.acknowledged
            and (project is None or a.project_id == project)
            and (task is None or a.task_id == task)
        ]
    else:
        print(
            f"{RED}✗{RESET} Uso: alerts ack <n> [<n>...] | --all [--project <id>] [--task <id>]",
            file=sys.stderr,
        )
        sys.exit(1)

    if not targets:
        print("Nenhum alerta correspondente.")
        return

    for alert in targets:
        alert.acknowledged = True
    _save(alerts)
    print(f"{GREEN}✓{RESET} {len(targets)} alerta(s) reconhecido(s).")


def cmd_rm(
    indexes: list[str],
    rm_acked: bool = False,
    rm_all: bool = False,
) -> None:
    alerts = ckpt.load_alerts()

    if indexes:
        targets = _resolve_indexes(alerts, indexes)
    elif rm_acked:
        targets = [a for a in alerts.alerts if a.acknowledged]
    elif rm_all:
        targets = list(alerts.alerts)
    else:
        print(
            f"{RED}✗{RESET} Uso: alerts rm <n> [<n>...] | --acked | --all",
            file=sys.stderr,
        )
        sys.exit(1)

    if not targets:
        print("Nenhum alerta correspondente.")
        return

    target_ids = {id(a) for a in targets}
    alerts.alerts = [a for a in alerts.alerts if id(a) not in target_ids]
    _save(alerts)
    print(f"{GREEN}✓{RESET} {len(targets)} alerta(s) removido(s).")


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    sys.path.insert(0, str(Path(__file__).parent))

    if len(sys.argv) < 2:
        cmd_list()
        return

    subcmd = sys.argv[1]
    args = sys.argv[2:]

    if subcmd in ("-h", "--help", "help"):
        _print_help()
        return

    if subcmd == "list":
        cmd_list(show_all="--all" in args, project=_get_flag(args, "--project"))

    elif subcmd == "ack":
        indexes = [a for a in args if not a.startswith("--") and not _is_flag_value(args, a)]
        cmd_ack(
            indexes,
            ack_all="--all" in args,
            project=_get_flag(args, "--project"),
            task=_get_flag(args, "--task"),
        )

    elif subcmd == "rm":
        indexes = [a for a in args if not a.startswith("--")]
        cmd_rm(indexes, rm_acked="--acked" in args, rm_all="--all" in args)

    else:
        print(f"{RED}✗{RESET} Subcomando desconhecido: '{subcmd}'", file=sys.stderr)
        _print_help()
        sys.exit(1)


def _get_flag(args: list[str], flag: str) -> Optional[str]:
    """Extrai o valor de uma flag --key value dos args."""
    try:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    except ValueError:
        pass
    return None


def _is_flag_value(args: list[str], token: str) -> bool:
    """True se o token é o valor de uma flag --key (ex: o 'x' em '--project x')."""
    try:
        idx = args.index(token)
    except ValueError:
        return False
    return idx > 0 and args[idx - 1].startswith("--")


def _print_help() -> None:
    print(f"""
{BOLD}squire alerts{RESET} — gerenciamento de alertas

  {CYAN}squire alerts{RESET}                               Lista alertas pendentes (alias de list)
  {CYAN}squire alerts list{RESET} [--all] [--project <id>]  Lista alertas (--all inclui reconhecidos)
  {CYAN}squire alerts ack{RESET}  <n> [<n>...]              Reconhece alertas por índice
  {CYAN}squire alerts ack{RESET}  --all [--project <id>] [--task <id>]
                                              Reconhece todos (com filtros opcionais)
  {CYAN}squire alerts rm{RESET}   <n> [<n>...]              Remove alertas por índice
  {CYAN}squire alerts rm{RESET}   --acked | --all           Remove reconhecidos / todos

Índices referem-se à lista de não-reconhecidos. Com o dashboard ativo
(segundo escritor), prefira os seletores --project/--task.
""")


if __name__ == "__main__":
    main()
