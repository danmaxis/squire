"""
Operações git compartilhadas (orquestrador + squire fix).
Todas guarded: nunca levantam — devolvem um status legível para log.
"""

from __future__ import annotations

import subprocess


def commit_all(repo_path: str, message: str) -> str:
    """git add -A + commit no repo. Retorna 'committed' | 'nothing' | 'failed: …'.

    Tolera repo sem HEAD (primeiro commit) e working tree limpo.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        if status.returncode != 0:
            return f"failed: {status.stderr.strip()[:120] or 'não é um repo git'}"
        if not status.stdout.strip():
            return "nothing"

        add = subprocess.run(
            ["git", "add", "-A"], cwd=repo_path, capture_output=True, text=True, timeout=15
        )
        if add.returncode != 0:
            return f"failed: git add: {add.stderr.strip()[:120] or 'erro desconhecido'}"
        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
        if commit.returncode == 0:
            return "committed"
        if "nothing to commit" in commit.stdout + commit.stderr:
            return "nothing"
        return f"failed: {commit.stderr.strip()[:120]}"
    except Exception as e:
        return f"failed: {e}"
