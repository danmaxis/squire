#!/usr/bin/env python3
"""
CLI para gerenciamento de tasks de projetos do squire.
Invocado por 'squire tasks <subcmd> <projeto> [args]'.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import checkpoint as ckpt
import config
from models import Effort, Subtask, Task, TaskList, TaskStatus, TestAuthor

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


# ── Helpers ────────────────────────────────────────────────────────

STATUS_ICON = {
    TaskStatus.pending: _c(CYAN, "→"),
    TaskStatus.implementing: _c(YELLOW, "~"),
    TaskStatus.testing: _c(YELLOW, "~"),
    TaskStatus.homologating: _c(YELLOW, "~"),
    TaskStatus.completed: _c(GREEN, "✓"),
    TaskStatus.blocked: _c(RED, "✗"),
}


def _load_project_or_exit(project_id: str):
    project = ckpt.load_project(project_id)
    if project is None:
        print(f"{RED}✗{RESET} Projeto '{project_id}' não encontrado em {config.PROJECTS_DIR}", file=sys.stderr)
        sys.exit(1)
    return project


def _load_tasks(project_id: str) -> TaskList:
    return ckpt.load_tasks(project_id)


def _save_tasks(project_id: str, task_list: TaskList) -> None:
    ckpt.save_tasks(project_id, task_list)


def _find_task(task_list: TaskList, task_id: str) -> Optional[Task]:
    for t in task_list.tasks:
        if t.id == task_id:
            return t
    return None


def _next_task_id(task_list: TaskList) -> str:
    """Gera o próximo ID sequencial no formato task-NNN."""
    existing_ids = {t.id for t in task_list.tasks}
    n = len(task_list.tasks) + 1
    while True:
        candidate = f"task-{n:03d}"
        if candidate not in existing_ids:
            return candidate
        n += 1


def _call_claude(prompt: str, timeout: int = 120) -> Optional[str]:
    """Chama claude --print e retorna o conteúdo da resposta, ou None em erro."""
    try:
        result = subprocess.run(
            [config.CLAUDE_CODE_BIN, "--print", "--output-format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"{RED}✗{RESET} Claude não respondeu em {timeout}s.", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"{RED}✗{RESET} Claude não encontrado: {config.CLAUDE_CODE_BIN}", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(f"{RED}✗{RESET} Claude retornou código {result.returncode}:\n{result.stderr[:400]}", file=sys.stderr)
        return None

    raw = result.stdout.strip()
    if not raw:
        print(f"{RED}✗{RESET} Claude retornou resposta vazia.", file=sys.stderr)
        return None

    # Desempacotar o envelope JSON do --output-format json
    try:
        envelope = json.loads(raw)
        content = envelope.get("result") or envelope.get("content") or raw
        if isinstance(content, str):
            return content
        # Se content for dict/list, serializar de volta
        return json.dumps(content, ensure_ascii=False)
    except json.JSONDecodeError:
        # Resposta não veio em envelope — usar direto
        return raw


def _parse_json_from_response(text: str) -> Optional[dict | list]:
    """Tenta parsear JSON da resposta, removendo markdown fences se necessário."""
    clean = text.strip()
    # Remover markdown fences
    if clean.startswith("```"):
        lines = clean.split("\n", 1)
        clean = lines[1] if len(lines) > 1 else clean
        clean = clean.rsplit("```", 1)[0].strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return None


# ── Subcomandos ────────────────────────────────────────────────────

def cmd_list(project_id: str) -> None:
    _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)

    if not task_list.tasks:
        print(f"{DIM}(nenhuma task){RESET}")
        return

    print(f"\n{BOLD}Tasks: {project_id}{RESET}\n")

    counts = {s: 0 for s in TaskStatus}
    for task in task_list.tasks:
        icon = STATUS_ICON.get(task.status, "?")
        status_str = _c(DIM, task.status.value)
        attempts_str = ""
        if task.attempts > 0 or task.homologation_attempt > 0:
            attempts_str = _c(DIM, f"  ({task.attempts} att, {task.homologation_attempt} rounds)")
        subtasks_str = ""
        if task.subtasks:
            subtasks_str = _c(DIM, f"  [{len(task.subtasks)} subtasks]")
        skip_str = _c(DIM, "  [skip-homolog]") if task.skip_homologation else ""
        print(f"  {icon}  {BOLD}{task.id}{RESET}  {task.title}  {status_str}{attempts_str}{subtasks_str}{skip_str}")
        counts[task.status] += 1

    total = len(task_list.tasks)
    done = counts[TaskStatus.completed]
    blocked = counts[TaskStatus.blocked]
    pending = counts[TaskStatus.pending]
    print(f"\n{DIM}Total: {total}  ✓ {done}  ✗ {blocked}  → {pending} pendente(s){RESET}\n")


def _prompt_advanced_fields(
    effort: Effort = Effort.medium,
    tdd: bool = True,
    test_author: TestAuthor = TestAuthor.claude,
) -> tuple[Effort, bool, TestAuthor]:
    """Pergunta campos avançados ao usuário. Enter aceita os padrões."""
    try:
        resp = input(f"  Configurar campos avançados? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return effort, tdd, test_author

    if resp != "y":
        return effort, tdd, test_author

    # effort
    try:
        v = input(f"  effort [low/medium/high] (padrão: {effort.value}): ").strip().lower()
        if v in ("low", "medium", "high"):
            effort = Effort(v)
    except (EOFError, KeyboardInterrupt):
        pass

    # tdd
    try:
        v = input(f"  tdd [y/n] (padrão: {'y' if tdd else 'n'}): ").strip().lower()
        if v in ("y", "n"):
            tdd = v == "y"
    except (EOFError, KeyboardInterrupt):
        pass

    # test_author (só relevante se tdd=True)
    if tdd:
        try:
            v = input(f"  test_author [claude/local] (padrão: {test_author.value}): ").strip().lower()
            if v in ("claude", "local"):
                test_author = TestAuthor(v)
        except (EOFError, KeyboardInterrupt):
            pass

    return effort, tdd, test_author


def cmd_add(
    project_id: str,
    title: str,
    desc: str = "",
    task_id: Optional[str] = None,
    skip_homologation: bool = False,
    max_attempts: int = 10,
    max_homologation_attempts: int = 5,
    effort: Effort = Effort.medium,
    tdd: bool = True,
    test_author: TestAuthor = TestAuthor.claude,
    ask_advanced: bool = True,
    spec: Optional[bool] = None,
) -> None:
    _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)

    # Gerar ID se não fornecido
    if not task_id:
        task_id = _next_task_id(task_list)
    elif _find_task(task_list, task_id) is not None:
        print(f"{RED}✗{RESET} ID '{task_id}' já existe.", file=sys.stderr)
        sys.exit(1)

    if ask_advanced:
        effort, tdd, test_author = _prompt_advanced_fields(effort, tdd, test_author)

    task = Task(
        id=task_id,
        title=title,
        description=desc,
        skip_homologation=skip_homologation,
        max_attempts=max_attempts,
        max_homologation_attempts=max_homologation_attempts,
        effort=effort,
        tdd=tdd,
        test_author=test_author,
    )
    task_list.tasks.append(task)
    _save_tasks(project_id, task_list)

    effort_str = _c(DIM, f"  [{effort.value}{'  tdd:' + test_author.value if tdd else '  no-tdd'}]")
    print(f"{GREEN}✓{RESET} Task '{task_id}' adicionada: {title}{effort_str}")

    # Oferecer atualizar SPEC.md
    _offer_spec_update(project_id, choice=spec)


def _offer_spec_update(project_id: str, choice: Optional[bool] = None) -> None:
    """Oferece atualizar SPEC.md após mudança nas tasks.

    choice=True roda sem perguntar; choice=False pula silenciosamente;
    choice=None mantém o prompt interativo.
    """
    spec_path = _get_spec_path(project_id)
    if not spec_path.exists():
        return
    if choice is False:
        return
    if choice is None:
        try:
            resp = input("  Atualizar SPEC.md? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if resp != "y":
            return
    cmd_spec_update(project_id)


def _session_lock_alive() -> bool:
    """True se há um session.lock com pid vivo."""
    from models import SessionLock
    lock = ckpt.load_model(config.SESSION_LOCK_FILE, SessionLock)
    if lock is None or not lock.pid:
        return False
    try:
        os.kill(lock.pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _get_spec_path(project_id: str) -> "Path":
    """Retorna o caminho do SPEC.md do projeto (dentro do repo do projeto)."""
    from pathlib import Path
    project = ckpt.load_project(project_id)
    if project and project.repo_path:
        return Path(project.repo_path) / "docs" / "SPEC.md"
    return config.project_dir(project_id) / "SPEC.md"


def cmd_spec_update(project_id: str) -> None:
    """Regenera o SPEC.md a partir das tasks atuais via Claude."""
    project = _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)
    spec_path = _get_spec_path(project_id)

    existing_spec = ""
    if spec_path.exists():
        existing_spec = spec_path.read_text(encoding="utf-8")

    tasks_summary = "\n".join(
        f"- [{t.status.value}] {t.id}: {t.title}"
        + (f" [{t.effort.value}]" if hasattr(t, "effort") else "")
        + (" [tdd]" if getattr(t, "tdd", False) else "")
        for t in task_list.tasks
    )

    existing_section = (
        f"\n\nSPEC.md atual (atualize refletindo as mudanças):\n{existing_spec[:2000]}"
        if existing_spec else ""
    )

    prompt = (
        f"Gere (ou atualize) o SPEC.md do projeto abaixo com base nas tasks.\n\n"
        f"Projeto: {project.name}\n"
        f"Descrição: {project.description}\n"
        f"Stack: {', '.join(project.stack) if project.stack else 'não especificado'}\n\n"
        f"Tasks ({len(task_list.tasks)}):\n{tasks_summary}"
        f"{existing_section}\n\n"
        f"Escreva um SPEC.md narrativo em português cobrindo: objetivo, funcionalidades, "
        f"stack, e lista de tasks com breve descrição de cada uma."
    )

    print(f"\n{CYAN}→{RESET} Gerando SPEC.md para '{project.name}'...\n")
    raw = _call_claude(prompt, timeout=120)
    if raw is None:
        print(f"{RED}✗{RESET} Claude não respondeu.", file=sys.stderr)
        return

    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(raw, encoding="utf-8")
    print(f"{GREEN}✓{RESET} SPEC.md salvo em {spec_path}")


def cmd_edit(project_id: str, task_id: Optional[str] = None) -> None:
    _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)
    editor = os.environ.get("EDITOR", "nano")

    if task_id is None:
        # Editar o tasks.json inteiro
        tasks_path = config.project_dir(project_id) / "tasks.json"
        if not tasks_path.exists():
            # Criar arquivo vazio para o editor
            _save_tasks(project_id, task_list)
        os.execvp(editor, [editor, str(tasks_path)])  # substitui o processo
        return

    # Editar uma task isolada em arquivo temporário
    task = _find_task(task_list, task_id)
    if task is None:
        print(f"{RED}✗{RESET} Task '{task_id}' não encontrada.", file=sys.stderr)
        sys.exit(1)

    task_json = json.dumps(task.model_dump(mode="json"), indent=2, ensure_ascii=False)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix=f"squire-task-{task_id}-",
        delete=False, encoding="utf-8"
    ) as f:
        f.write(task_json)
        tmp_path = f.name

    try:
        subprocess.run([editor, tmp_path], check=True)

        with open(tmp_path, encoding="utf-8") as f:
            edited = f.read()

        # Validar e substituir na lista
        try:
            updated_task = Task.model_validate_json(edited)
        except Exception as e:
            print(f"{RED}✗{RESET} JSON inválido após edição: {e}", file=sys.stderr)
            sys.exit(1)

        task_list.tasks = [updated_task if t.id == task_id else t for t in task_list.tasks]
        _save_tasks(project_id, task_list)
        print(f"{GREEN}✓{RESET} Task '{task_id}' atualizada.")
        _offer_spec_update(project_id)

    finally:
        os.unlink(tmp_path)


def cmd_rm(project_id: str, task_id: str, assume_yes: bool = False) -> None:
    _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)

    task = _find_task(task_list, task_id)
    if task is None:
        print(f"{RED}✗{RESET} Task '{task_id}' não encontrada.", file=sys.stderr)
        sys.exit(1)

    print(f"  Remover: {BOLD}{task.id}{RESET}  {task.title}  [{task.status.value}]")
    if not assume_yes:
        try:
            resp = input("  Confirmar? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(0)

        if resp != "y":
            print("Cancelado.")
            sys.exit(0)

    task_list.tasks = [t for t in task_list.tasks if t.id != task_id]
    _save_tasks(project_id, task_list)
    print(f"{GREEN}✓{RESET} Task '{task_id}' removida.")


def cmd_split(project_id: str, task_id: str, assume_yes: bool = False) -> None:
    project = _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)

    task = _find_task(task_list, task_id)
    if task is None:
        print(f"{RED}✗{RESET} Task '{task_id}' não encontrada.", file=sys.stderr)
        sys.exit(1)

    stack_str = ", ".join(project.stack) if project.stack else "não especificado"
    print(f"\n{CYAN}→{RESET} Pedindo ao Claude para subdividir '{task.title}'...\n")

    def _build_split_prompt(feedback: str = "") -> str:
        feedback_section = f"\n\nFeedback do usuário na proposta anterior:\n{feedback}" if feedback else ""
        return (
            f"Subdivida a seguinte task em subtasks menores e implementáveis de forma independente.\n\n"
            f"Projeto: {project.name}\n"
            f"Stack: {stack_str}\n"
            f"Task: {task.title} [effort={task.effort.value}, tdd={task.tdd}]\n"
            f"Descrição: {task.description or '(sem descrição)'}\n"
            f"{feedback_section}\n\n"
            f"Para cada subtask, defina effort e tdd individualmente (podem diferir da task pai).\n"
            f"Responda APENAS com JSON válido, sem markdown:\n"
            f'{{\"subtasks\": [{{"title": "...", "description": "...", '
            f'"effort": "low|medium|high", "tdd": true|false}}, ...]}}'
        )

    def _call_and_parse(feedback: str = "") -> Optional[list[dict]]:
        raw = _call_claude(_build_split_prompt(feedback))
        if raw is None:
            return None
        parsed = _parse_json_from_response(raw)
        if not isinstance(parsed, dict) or "subtasks" not in parsed:
            print(f"{YELLOW}⚠{RESET} Resposta inesperada do Claude:\n{raw[:500]}", file=sys.stderr)
            return None
        return parsed["subtasks"]

    subtasks_data = _call_and_parse()
    if subtasks_data is None:
        sys.exit(1)

    def _display_subtasks(data: list[dict]) -> None:
        print(f"\n{BOLD}Subtasks propostas:{RESET}")
        for i, st in enumerate(data, 1):
            print(f"  {i}. {BOLD}{st.get('title', '?')}{RESET}")
            if st.get("description"):
                print(f"     {DIM}{st['description']}{RESET}")

    # --yes: aceita a primeira proposta sem confirmação
    confirm_rounds = 0 if assume_yes else 2
    if assume_yes:
        _display_subtasks(subtasks_data)

    # Loop de confirmação (máximo 1 refinamento)
    for attempt in range(confirm_rounds):
        _display_subtasks(subtasks_data)

        try:
            resp = input(f"\n  Confirmar? [y/n/feedback] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(0)

        if resp.lower() == "y" or resp == "":
            break
        if resp.lower() == "n":
            print("Cancelado.")
            sys.exit(0)
        # Feedback — refinar (só na primeira iteração)
        if attempt == 0:
            print(f"\n{CYAN}→{RESET} Refinando com seu feedback...\n")
            subtasks_data = _call_and_parse(feedback=resp)
            if subtasks_data is None:
                sys.exit(1)
        else:
            # Segunda iteração esgotada — salvar o que temos
            break

    # Salvar subtasks na task
    subtasks = []
    for i, st in enumerate(subtasks_data, 1):
        try:
            st_effort = Effort(st.get("effort", task.effort.value))
        except ValueError:
            st_effort = task.effort
        subtasks.append(Subtask(
            id=f"{task_id}-sub{i:02d}",
            title=st.get("title", f"Subtask {i}"),
        ))
    task.subtasks = subtasks

    task_list.tasks = [task if t.id == task_id else t for t in task_list.tasks]
    _save_tasks(project_id, task_list)
    print(f"\n{GREEN}✓{RESET} {len(subtasks)} subtask(s) salva(s) em '{task_id}'.")


def cmd_plan(
    project_id: str,
    desc: Optional[str] = None,
    mode: Optional[str] = None,
    refine: bool = True,
    assume_yes: bool = False,
    spec: Optional[bool] = None,
) -> None:
    project = _load_project_or_exit(project_id)
    task_list = _load_tasks(project_id)

    # --yes implica fluxo sem prompts: sem refinamento, SPEC só com --spec explícito
    if assume_yes:
        refine = False
        if spec is None:
            spec = False
        # Não competir com uma sessão ativa pelo tasks.json (o squire grava
        # de volta a cada transição e sobrescreveria o plano)
        if _session_lock_alive():
            print(
                f"{RED}✗{RESET} Sessão squire ativa — plan --yes recusado para "
                f"não disputar o tasks.json. Aguarde ou use 'squire kill'.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Coletar descrição se não fornecida
    if not desc and not project.description:
        if assume_yes:
            print(f"{YELLOW}⚠{RESET} Sem descrição (--desc) — usando o nome do projeto como base.")
        else:
            print(f"{CYAN}→{RESET} Descreva o que o projeto deve fazer (Enter em branco para usar o nome do projeto):")
            try:
                desc = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelado.")
                sys.exit(0)

    effective_desc = desc or project.description or project.name
    stack_str = ", ".join(project.stack) if project.stack else "não especificado"

    # Contexto de tasks existentes
    existing_section = ""
    if task_list.tasks:
        lines = [f"\nTasks já existentes ({len(task_list.tasks)}):"]
        for t in task_list.tasks:
            lines.append(f"  - [{t.status.value}] {t.id}: {t.title}")
        existing_section = "\n".join(lines)

    def _build_plan_prompt(feedback: str = "", current_draft: str = "") -> str:
        feedback_section = ""
        if feedback and current_draft:
            feedback_section = (
                f"\n\nRascunho anterior:\n{current_draft}\n\n"
                f"Feedback do usuário (incorpore e melhore):\n{feedback}"
            )
        return (
            f"Planeje as tasks de implementação para o seguinte projeto.\n\n"
            f"Projeto: {project.name}\n"
            f"Descrição: {effective_desc}\n"
            f"Stack: {stack_str}\n"
            f"{existing_section}"
            f"{feedback_section}\n\n"
            f"Gere uma lista de tasks implementáveis sequencialmente, cada uma clara e autocontida.\n"
            f"Para tasks de setup/boilerplate sem necessidade de review de qualidade, use skip_homologation: true.\n\n"
            f"Responda APENAS com JSON válido, sem markdown:\n"
            f'{{"tasks": [{{"id": "task-001", "title": "...", "description": "...", '
            f'"effort": "low|medium|high", "tdd": true|false, '
            f'"test_author": "claude|local", '
            f'"max_attempts": 10, "max_homologation_attempts": 5, "skip_homologation": false}}, ...]}}'
        )

    def _call_and_parse_plan(feedback: str = "", draft: str = "") -> Optional[list[dict]]:
        raw = _call_claude(_build_plan_prompt(feedback, draft), timeout=180)
        if raw is None:
            return None
        parsed = _parse_json_from_response(raw)
        if not isinstance(parsed, dict) or "tasks" not in parsed:
            print(f"{YELLOW}⚠{RESET} Resposta inesperada do Claude:\n{raw[:600]}", file=sys.stderr)
            return None
        return parsed["tasks"], raw  # type: ignore[return-value]

    print(f"\n{CYAN}→{RESET} Gerando rascunho de tasks para '{project.name}'...\n")

    result = _call_and_parse_plan()
    if result is None:
        sys.exit(1)
    tasks_data, last_raw = result

    MAX_REFINEMENTS = 3 if refine else 0

    for iteration in range(MAX_REFINEMENTS + 1):
        _display_draft(tasks_data)

        if iteration == MAX_REFINEMENTS:
            if refine:
                print(f"{YELLOW}⚠{RESET} Limite de {MAX_REFINEMENTS} refinamentos atingido.")
                print("  Salvando rascunho atual.")
            break

        try:
            resp = input(
                f"\n  Feedback (Enter/'ok' para salvar, 'cancel' para abortar):\n  > "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelado.")
            sys.exit(0)

        if resp.lower() in ("ok", "done", ""):
            break
        if resp.lower() == "cancel":
            print("Cancelado.")
            sys.exit(0)

        print(f"\n{CYAN}→{RESET} Refinando...\n")
        result = _call_and_parse_plan(feedback=resp, draft=last_raw)
        if result is None:
            print(f"{YELLOW}⚠{RESET} Falha no refinamento — mantendo rascunho anterior.")
            break
        tasks_data, last_raw = result

    # Resolver replace ou append (--mode > prompt; Enter = adicionar)
    if mode in ("append", "a"):
        mode = "a"
    elif mode in ("replace", "r"):
        mode = "r"
    elif task_list.tasks:
        if assume_yes:
            mode = "a"  # default não-destrutivo
        else:
            print(f"\n  Tasks existentes: {len(task_list.tasks)}")
            try:
                mode = input("  Substituir ou adicionar? [r/a] (Enter=adicionar) ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nCancelado.")
                sys.exit(0)
            if mode == "":
                mode = "a"
            if mode not in ("r", "a"):
                print(f"{YELLOW}⚠{RESET} Opção inválida — operação cancelada.")
                sys.exit(1)
    else:
        mode = "r"  # sem tasks existentes, sempre substituir

    # Construir tasks Pydantic
    new_tasks = []
    existing_ids = {t.id for t in task_list.tasks}

    for raw_task in tasks_data:
        tid = raw_task.get("id") or _next_task_id(TaskList(tasks=task_list.tasks + new_tasks))
        # Evitar colisão de IDs no modo append
        if mode == "a" and tid in existing_ids:
            tid = _next_task_id(TaskList(tasks=task_list.tasks + new_tasks))
        # Parsear effort e test_author com fallback seguro
        effort_val = raw_task.get("effort", "medium")
        try:
            effort = Effort(effort_val)
        except ValueError:
            effort = Effort.medium
        test_author_val = raw_task.get("test_author", "claude")
        try:
            test_author = TestAuthor(test_author_val)
        except ValueError:
            test_author = TestAuthor.claude
        new_tasks.append(Task(
            id=tid,
            title=raw_task.get("title", "Sem título"),
            description=raw_task.get("description", ""),
            max_attempts=raw_task.get("max_attempts", 10),
            max_homologation_attempts=raw_task.get("max_homologation_attempts", 5),
            skip_homologation=raw_task.get("skip_homologation", False),
            effort=effort,
            tdd=raw_task.get("tdd", True),
            test_author=test_author,
        ))

    if mode == "r":
        task_list.tasks = new_tasks
    else:
        task_list.tasks = task_list.tasks + new_tasks

    _save_tasks(project_id, task_list)
    action = "substituídas por" if mode == "r" else "adicionadas:"
    print(f"\n{GREEN}✓{RESET} Tasks {action} {len(new_tasks)} nova(s).")

    # Oferecer salvar SPEC.md (--spec roda direto, --no-spec/--yes pula)
    if spec is True:
        cmd_spec_update(project_id)
    elif spec is None:
        try:
            resp = input("\n  Salvar SPEC.md? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resp = ""
        if resp == "y":
            cmd_spec_update(project_id)


def _display_draft(tasks_data: list[dict]) -> None:
    print(f"\n{BOLD}Rascunho ({len(tasks_data)} tasks):{RESET}")
    for i, t in enumerate(tasks_data, 1):
        skip = " [skip-homolog]" if t.get("skip_homologation") else ""
        print(f"  {i:2}. {BOLD}{t.get('id', f'task-{i:03d}')}{RESET}  {t.get('title', '?')}{_c(DIM, skip)}")
        if t.get("description"):
            desc = t["description"]
            if len(desc) > 120:
                desc = desc[:117] + "..."
            print(f"      {DIM}{desc}{RESET}")


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    # Garantir que o pythonpath inclui o diretório do script
    sys.path.insert(0, str(Path(__file__).parent))

    if len(sys.argv) < 2:
        _print_help()
        sys.exit(1)

    subcmd = sys.argv[1]
    args = sys.argv[2:]

    if subcmd in ("-h", "--help", "help"):
        _print_help()
        return

    if subcmd == "list":
        if not args:
            print(f"{RED}✗{RESET} Projeto obrigatório.", file=sys.stderr)
            sys.exit(1)
        cmd_list(args[0])

    elif subcmd == "add":
        if not args:
            print(f"{RED}✗{RESET} Projeto obrigatório.", file=sys.stderr)
            sys.exit(1)
        project_id = args[0]
        rest = args[1:]
        # Parse manual de flags
        title = _get_flag(rest, "--title")
        if not title:
            print(f"{RED}✗{RESET} --title obrigatório.", file=sys.stderr)
            sys.exit(1)
        desc = _get_flag(rest, "--desc") or ""
        task_id = _get_flag(rest, "--id")
        skip = "--skip-homolog" in rest
        max_att = int(_get_flag(rest, "--max") or "10")
        max_hom = int(_get_flag(rest, "--max-homolog") or "5")
        effort_str = _get_flag(rest, "--effort") or "medium"
        try:
            effort = Effort(effort_str)
        except ValueError:
            effort = Effort.medium
        tdd = "--no-tdd" not in rest
        test_author_str = _get_flag(rest, "--test-author") or "claude"
        try:
            test_author = TestAuthor(test_author_str)
        except ValueError:
            test_author = TestAuthor.claude
        no_ask = "--no-ask" in rest
        spec = True if "--spec" in rest else (False if "--no-spec" in rest else None)
        cmd_add(project_id, title, desc, task_id, skip, max_att, max_hom,
                effort, tdd, test_author, ask_advanced=not no_ask, spec=spec)

    elif subcmd == "edit":
        if not args:
            print(f"{RED}✗{RESET} Projeto obrigatório.", file=sys.stderr)
            sys.exit(1)
        project_id = args[0]
        task_id = args[1] if len(args) > 1 else None
        cmd_edit(project_id, task_id)

    elif subcmd == "rm":
        if len(args) < 2:
            print(f"{RED}✗{RESET} Uso: tasks rm <projeto> <id> [--yes]", file=sys.stderr)
            sys.exit(1)
        cmd_rm(args[0], args[1], assume_yes="--yes" in args[2:])

    elif subcmd == "split":
        if len(args) < 2:
            print(f"{RED}✗{RESET} Uso: tasks split <projeto> <id> [--yes]", file=sys.stderr)
            sys.exit(1)
        cmd_split(args[0], args[1], assume_yes="--yes" in args[2:])

    elif subcmd == "plan":
        if not args:
            print(f"{RED}✗{RESET} Projeto obrigatório.", file=sys.stderr)
            sys.exit(1)
        project_id = args[0]
        rest = args[1:]
        desc = _get_flag(rest, "--desc")
        mode = _get_flag(rest, "--mode")
        if mode is not None and mode not in ("append", "replace", "a", "r"):
            print(f"{RED}✗{RESET} --mode deve ser 'append' ou 'replace'.", file=sys.stderr)
            sys.exit(1)
        spec = True if "--spec" in rest else (False if "--no-spec" in rest else None)
        cmd_plan(
            project_id, desc,
            mode=mode,
            refine="--no-refine" not in rest,
            assume_yes="--yes" in rest,
            spec=spec,
        )

    elif subcmd == "spec":
        if not args:
            print(f"{RED}✗{RESET} Projeto obrigatório.", file=sys.stderr)
            sys.exit(1)
        cmd_spec_update(args[0])

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


def _print_help() -> None:
    print(f"""
{BOLD}squire tasks{RESET} — gerenciamento de tasks de um projeto

  {CYAN}squire tasks{RESET} <projeto>                    Lista tasks (alias de list)
  {CYAN}squire tasks list{RESET}   <projeto>              Lista tasks com status
  {CYAN}squire tasks add{RESET}    <projeto> --title "..." [--desc "..."] [--id "..."] [--skip-homolog] [--max N] [--max-homolog N] [--effort low|medium|high] [--no-tdd] [--test-author claude|local] [--no-ask] [--spec|--no-spec]
  {CYAN}squire tasks spec{RESET}   <projeto>              Gera/atualiza SPEC.md via Claude
  {CYAN}squire tasks edit{RESET}   <projeto> [<id>]       Edita task no $EDITOR (sem id = edita tasks.json)
  {CYAN}squire tasks rm{RESET}     <projeto> <id> [--yes]  Remove task por ID (--yes pula confirmação)
  {CYAN}squire tasks split{RESET}  <projeto> <id> [--yes]  Claude subdivide task (--yes aceita 1ª proposta)
  {CYAN}squire tasks plan{RESET}   <projeto> [--desc "..."] [--mode append|replace] [--no-refine] [--yes] [--spec|--no-spec]
                                              Claude planeja tasks (--yes = sem prompts, append por padrão)
""")


if __name__ == "__main__":
    main()
