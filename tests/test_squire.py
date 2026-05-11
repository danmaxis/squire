"""Testes unitários para o Squire — foco no ciclo de rodadas e productive wait."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from models import (
    Checkpoint,
    GlobalStats,
    LLMContextSummary,
    Project,
    ProjectStatus,
    RateLimitState,
    RecoveryHints,
    Task,
    TaskList,
    TaskStatus,
)


# ── Helpers ─────────────────────────────────────────────────────────

def make_task(**kwargs) -> Task:
    defaults = dict(
        id="task-001", title="Test task", description="Do something",
        status=TaskStatus.pending, attempts=0, max_attempts=10,
        homologation_attempt=0, max_homologation_attempts=5,
    )
    defaults.update(kwargs)
    return Task(**defaults)


def make_squire(can_call_side_effect=None):
    """
    Cria um Squire com todas as dependências externas mockadas.
    """
    from squire import Squire

    project = Project(
        id="test-proj", name="Test Project", description="Test",
        repo_path="/tmp/repo", status=ProjectStatus.implementing,
    )
    task_list = TaskList(tasks=[make_task()])
    cp = Checkpoint(session_id="sess-test")
    stats = GlobalStats()

    with (
        patch("squire.ckpt.load_project", return_value=project),
        patch("squire.ckpt.load_tasks", return_value=task_list),
        patch("squire.ckpt.load_checkpoint", return_value=cp),
        patch("squire.ckpt.load_stats", return_value=stats),
        patch("squire.InnerLoop"),
        patch("squire.Homologator"),
        patch("squire.TechnicalEscalation"),
    ):
        orch = Squire("test-proj", dry_run=False, verbose=False)

    # Substituir rate_limiter por mock controlável.
    # can_afford() (novo, cost-aware) e can_call() (legado) compartilham o side_effect
    # para que testes existentes continuem controlando "pode chamar agora?" sem alteração.
    orch.rate_limiter = MagicMock()
    if can_call_side_effect is not None:
        orch.rate_limiter.can_call.side_effect = list(can_call_side_effect)
        orch.rate_limiter.can_afford.side_effect = list(can_call_side_effect)
    else:
        orch.rate_limiter.can_call.return_value = True
        orch.rate_limiter.can_afford.return_value = True
    orch.rate_limiter.wait_seconds.return_value = 1500  # 25 min
    # state.max_daily_usd referenciado em _print_summary
    orch.rate_limiter.state.max_daily_usd = 0.0

    # Escalation retorna (texto/files, usage) — usage=None evita custo nos asserts
    orch.escalation.unblock.return_value = ("instrução do Claude", None)
    orch.escalation.implement_directly.return_value = ([], None)

    # Mock de _save_state para não tocar em disco
    orch._save_state = MagicMock()
    orch._record_event = MagicMock()

    # Isolar métodos que fazem subprocess/filesystem e seriam testados separadamente.
    # Testes específicos removem esses mocks para validar o comportamento real.
    orch._pre_homologation_checks = MagicMock(return_value=[])
    orch._commit_task_completion = MagicMock()

    return orch


def make_homolog_result(approved=True, feedback="ok", summary="", fix_suggestion="", error=None):
    r = MagicMock()
    r.approved = approved
    r.summary = summary
    r.feedback = feedback
    r.fix_suggestion = fix_suggestion
    r.error = error
    r.usage = None
    return r


# ── TestWaitProductively ─────────────────────────────────────────────

class TestWaitProductively:
    def test_nao_chama_inner_loop_quando_pode_chamar(self):
        """Se can_call() é True, não entra no loop produtivo."""
        orch = make_squire(can_call_side_effect=[True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "")

        orch._run_inner_loop.assert_not_called()

    def test_chama_inner_loop_uma_vez_durante_rate_limit(self):
        """Se can_call() retorna False uma vez e depois True, inner loop roda uma vez."""
        orch = make_squire(can_call_side_effect=[False, True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "feedback anterior")

        orch._run_inner_loop.assert_called_once_with(
            task, homologation_feedback="feedback anterior", test_hashes=None
        )

    def test_chama_inner_loop_multiplas_vezes_se_rate_limit_persiste(self):
        """Enquanto can_call() retorna False, continua rodando o inner loop."""
        orch = make_squire(can_call_side_effect=[False, False, False, True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "meu feedback")

        assert orch._run_inner_loop.call_count == 3
        for c in orch._run_inner_loop.call_args_list:
            assert c == call(task, homologation_feedback="meu feedback", test_hashes=None)

    def test_reseta_attempts_antes_de_cada_inner_loop(self):
        """task.attempts deve ser zerado antes de cada rodada do inner loop."""
        orch = make_squire(can_call_side_effect=[False, False, True])
        task = make_task(attempts=7)
        attempts_before_call = []

        def capture_attempts(*args, **kwargs):
            attempts_before_call.append(task.attempts)
            task.attempts = 5
            return True

        orch._run_inner_loop = capture_attempts

        orch._wait_productively(task, "")

        assert attempts_before_call == [0, 0]

    def test_feedback_vazio_funciona(self):
        """Feedback vazio não causa erro."""
        orch = make_squire(can_call_side_effect=[False, True])
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=False)

        orch._wait_productively(task, "")

        orch._run_inner_loop.assert_called_once_with(task, homologation_feedback="", test_hashes=None)

    def test_propaga_test_hashes_para_inner_loop(self):
        """test_hashes passado para _wait_productively deve chegar ao inner loop."""
        orch = make_squire(can_call_side_effect=[False, True])
        task = make_task()
        hashes = {"tests/test_foo.py": "abc123"}
        orch._run_inner_loop = MagicMock(return_value=True)

        orch._wait_productively(task, "", test_hashes=hashes)

        orch._run_inner_loop.assert_called_once_with(
            task, homologation_feedback="", test_hashes=hashes
        )


# ── TestRunHomologation ──────────────────────────────────────────────

class TestRunHomologation:
    """
    Com o novo design (Ralph Loop), _run_homologation:
    - Roda inner loop NO INÍCIO de cada rodada (não só na rejeição)
    - Sempre homologa, independente do resultado dos testes
    - max_homologation_attempts = número de rodadas completas
    """

    def test_aprovado_na_primeira_rodada(self):
        """Inner loop roda, homologação aprova → True."""
        orch = make_squire()
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time") as mock_time:
            result = orch._run_homologation(task)

        assert result is True
        assert task.homologation_result == "approved"
        orch._run_inner_loop.assert_called_once()

    def test_inner_loop_chamado_no_inicio_de_cada_rodada(self):
        """Inner loop deve ser chamado uma vez por rodada."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=3)
        orch._run_inner_loop = MagicMock(return_value=False)  # testes sempre falham
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="precisa melhorar"
        )

        with patch("squire.time"):
            orch._run_homologation(task)

        # 3 rodadas → 3 chamadas ao inner loop (uma por rodada)
        assert orch._run_inner_loop.call_count == 3

    def test_homologa_mesmo_com_testes_falhando(self):
        """Inner loop retorna False (testes falham) → homologação ainda ocorre."""
        orch = make_squire()
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=False)  # testes falham
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            result = orch._run_homologation(task)

        assert result is True
        orch.homologator.review.assert_called_once()

    def test_rejeitado_todas_rodadas_retorna_false(self):
        """Esgotando todas as rodadas sem aprovação → False."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=2)
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="não satisfaz"
        )

        with patch("squire.time"):
            result = orch._run_homologation(task)

        assert result is False
        assert task.homologation_result == "rejected"
        assert orch.homologator.review.call_count == 2

    def test_feedback_da_rejeicao_usado_na_rodada_seguinte(self):
        """Feedback da rejeição deve chegar como homologation_feedback no inner loop seguinte."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=2, tdd=False)

        inner_loop_feedbacks = []

        def capture_inner(t, homologation_feedback="", test_hashes=None):
            inner_loop_feedbacks.append(homologation_feedback)
            return True

        orch._run_inner_loop = capture_inner
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="falta empty state"),
            make_homolog_result(approved=True),
        ]

        with patch("squire.time"):
            orch._run_homologation(task)

        # Rodada 1: sem feedback anterior (ainda vazio)
        assert inner_loop_feedbacks[0] == ""
        # Rodada 2: contexto estruturado contendo o feedback da rejeição
        assert "falta empty state" in inner_loop_feedbacks[1]

    def test_productive_wait_chamado_antes_de_cada_homologacao(self):
        """_wait_productively deve ser chamado antes de cada chamada ao homologador."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=3)
        orch._wait_productively = MagicMock()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="fb1"),
            make_homolog_result(approved=False, feedback="fb2"),
            make_homolog_result(approved=True),
        ]

        with patch("squire.time"):
            orch._run_homologation(task)

        # 3 rodadas → 3 chamadas ao _wait_productively
        assert orch._wait_productively.call_count == 3

    def test_aprovado_na_terceira_rodada(self):
        """Aprovação na terceira rodada → True, tentativas anteriores foram esgotadas."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=5)
        orch._run_inner_loop = MagicMock(return_value=False)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="fb1"),
            make_homolog_result(approved=False, feedback="fb2"),
            make_homolog_result(approved=True),
        ]

        with patch("squire.time"):
            result = orch._run_homologation(task)

        assert result is True
        assert task.homologation_attempt == 3
        assert orch._run_inner_loop.call_count == 3

    def test_attempts_resetado_no_inicio_de_cada_rodada(self):
        """task.attempts deve ser zerado no início de cada rodada."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=2, tdd=False)
        attempts_at_start = []

        def capture(t, homologation_feedback="", test_hashes=None):
            attempts_at_start.append(t.attempts)
            t.attempts = 7  # simula progresso dentro do inner loop
            return True

        orch._run_inner_loop = capture
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="x"
        )

        with patch("squire.time"):
            orch._run_homologation(task)

        assert attempts_at_start == [0, 0]

    def test_pausa_de_5s_antes_de_cada_homologacao(self):
        """Deve chamar time.sleep(5) antes de cada homologação."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=2)
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="fb"),
            make_homolog_result(approved=True),
        ]

        with patch("squire.time") as mock_time:
            orch._run_homologation(task)

        assert mock_time.sleep.call_count == 2
        mock_time.sleep.assert_called_with(5)


# ── TestSkipHomologation ─────────────────────────────────────────────

class TestSkipHomologation:
    """
    Tasks com skip_homologation=True devem ser auto-aprovadas após o inner loop,
    sem chamar o homologador.
    """

    def test_skip_homologation_auto_aprova_sem_chamar_cc(self):
        """Com skip_homologation=True, aprovação ocorre sem chamar homologator.review."""
        orch = make_squire()
        task = make_task(skip_homologation=True)
        orch._run_inner_loop = MagicMock(return_value=True)

        with patch("squire.time"):
            result = orch._run_homologation(task)

        assert result is True
        assert task.homologation_result == "approved"
        orch.homologator.review.assert_not_called()

    def test_skip_homologation_registra_evento_aprovado(self):
        """Auto-aprovação deve registrar evento homologation_approved."""
        from models import EventType, Actor
        orch = make_squire()
        task = make_task(skip_homologation=True)
        orch._run_inner_loop = MagicMock(return_value=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        orch._record_event.assert_any_call(
            EventType.homologation_approved,
            task.id,
            1,
            "Auto-aprovado: skip_homologation=True",
            Actor.squire,
        )

    def test_sem_skip_homologation_chama_cc_normalmente(self):
        """Com skip_homologation=False (default), homologator.review é chamado."""
        orch = make_squire()
        task = make_task(skip_homologation=False)
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        orch.homologator.review.assert_called_once()


# ── TestAutoSnapshotCommit ───────────────────────────────────────────

class TestAutoSnapshotCommit:
    """
    _auto_snapshot_commit(task_id) protege o working tree criando um commit
    antes de cada task — ao invés de descartar alterações com git checkout.
    """

    def _proc(self, returncode=0, stdout="", stderr=""):
        return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_nao_faz_nada_quando_git_limpo(self):
        """Se working tree está limpo (porcelain vazio), nenhum commit é criado."""
        orch = make_squire()

        with patch("squire.subprocess.run") as mock_run:
            mock_run.return_value = self._proc(stdout="")
            orch._auto_snapshot_commit("task-001")

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "status", "--porcelain"] in calls
        assert not any("commit" in str(c) for c in calls)

    def test_faz_commit_quando_dirty_e_tem_commits(self):
        """Working tree sujo + repo com commits → cria commit de snapshot."""
        orch = make_squire()
        side_effects = [
            self._proc(stdout=" M src/index.ts\n?? tmp.py\n"),   # git status
            self._proc(returncode=0),                              # git rev-parse HEAD
            self._proc(),                                          # git add -A
            self._proc(returncode=0),                              # git commit
        ]
        with patch("squire.subprocess.run", side_effect=side_effects) as mock_run:
            orch._auto_snapshot_commit("task-007")

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "add", "-A"] in calls
        assert any("commit" in str(c) for c in calls)

    def test_mensagem_commit_contem_task_id(self):
        """A mensagem do commit deve conter o task_id e o prefixo 'chore: auto-snapshot before'."""
        orch = make_squire()
        commit_msgs = []

        def capture_run(cmd, **kwargs):
            if cmd[0] == "git" and "commit" in cmd:
                commit_msgs.append(cmd)
            return self._proc(returncode=0)

        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout=" M main.py\n"),   # status
            self._proc(returncode=0),              # rev-parse
            self._proc(),                          # git add
            self._proc(returncode=0),              # git commit (captured)
        ]):
            # Patch mais granular para capturar o commit
            pass

        # Testar diretamente com side_effect funcional
        orch2 = make_squire()
        with patch("squire.subprocess.run") as mock_run:
            mock_run.side_effect = [
                self._proc(stdout=" M main.py\n"),
                self._proc(returncode=0),
                self._proc(),
                self._proc(returncode=0),
            ]
            orch2._auto_snapshot_commit("task-abc")

        commit_call = next(
            c for c in mock_run.call_args_list
            if c.args[0][1] == "commit"
        )
        commit_cmd = commit_call.args[0]
        assert "chore: auto-snapshot before task-abc" in commit_cmd

    def test_pula_commit_sem_head(self):
        """Repo sem commits (HEAD não existe) — não tenta commitar."""
        orch = make_squire()
        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout="?? src/index.ts\n"),   # status: sujo
            self._proc(returncode=1),                   # rev-parse: sem HEAD
        ]) as mock_run:
            orch._auto_snapshot_commit("task-001")  # não deve lançar

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert not any("commit" in str(c) for c in calls)
        assert not any(c == ["git", "add", "-A"] for c in calls)

    def test_continua_se_git_status_retornar_erro(self):
        """git status com returncode != 0 → retorna sem lançar exceção."""
        orch = make_squire()
        with patch("squire.subprocess.run", return_value=self._proc(returncode=128, stderr="not a repo")):
            orch._auto_snapshot_commit("task-001")  # não deve lançar

    def test_continua_se_subprocess_lancar_excecao(self):
        """FileNotFoundError (git não instalado) → sem propagação."""
        orch = make_squire()
        with patch("squire.subprocess.run", side_effect=FileNotFoundError("git not found")):
            orch._auto_snapshot_commit("task-001")  # não deve lançar

    def test_nao_usa_checkout_para_limpar(self):
        """Nunca deve usar 'git checkout -- .' — isso destruiria alterações não commitadas."""
        orch = make_squire()
        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout=" M main.py\n"),
            self._proc(returncode=0),
            self._proc(),
            self._proc(returncode=0),
        ]) as mock_run:
            orch._auto_snapshot_commit("task-001")

        all_cmds = [str(c.args[0]) for c in mock_run.call_args_list]
        assert not any("checkout" in cmd for cmd in all_cmds)

    def test_auto_snapshot_chamado_antes_de_run_homologation(self):
        """_auto_snapshot_commit deve ser chamado antes de _run_homologation em run()."""
        orch = make_squire()
        task = make_task()

        call_order = []
        orch._auto_snapshot_commit = MagicMock(side_effect=lambda tid: call_order.append("snapshot"))
        orch._run_homologation = MagicMock(side_effect=lambda t: call_order.append("homolog") or True)
        orch._find_current_task = MagicMock(side_effect=[task, None])
        orch._record_event = MagicMock()
        orch._save_state = MagicMock()

        with (
            patch("squire.config.ensure_dirs"),
            patch("squire.ckpt.save_project"),
            patch("squire.ckpt.save_tasks"),
            patch("squire.ckpt.save_history"),
            patch("squire.ckpt.release_lock"),
            patch("squire.ckpt.acquire_lock"),
            patch("squire.threading"),
        ):
            orch.run()

        assert call_order.index("snapshot") < call_order.index("homolog")


# ── TestCommitTaskCompletion ─────────────────────────────────────────

class TestCommitTaskCompletion:
    """
    _commit_task_completion(task) commita as alterações aprovadas após homologação.
    Garante que o trabalho aprovado está no git antes do próximo agente iniciar.
    """

    def _proc(self, returncode=0, stdout="", stderr=""):
        return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)

    def _make_orch(self):
        """Cria Squire com _commit_task_completion real (não mockado)."""
        from squire import Squire
        orch = make_squire()
        orch._commit_task_completion = lambda task: Squire._commit_task_completion(orch, task)
        return orch

    def test_commita_quando_dirty_com_commits(self):
        """Working tree sujo + repo com commits → commit com mensagem feat:."""
        orch = self._make_orch()
        task = make_task(id="task-001", title="Test task")

        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout=" M src/foo.ts\n"),  # status: sujo
            self._proc(returncode=0),               # rev-parse: tem HEAD
            self._proc(),                            # git add
            self._proc(returncode=0),               # git commit
        ]) as mock_run:
            orch._commit_task_completion(task)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["git", "add", "-A"] in calls
        assert any("commit" in str(c) for c in calls)

    def test_nao_faz_nada_quando_clean(self):
        """Working tree limpo → retorna sem commitar."""
        orch = self._make_orch()
        task = make_task()

        with patch("squire.subprocess.run", return_value=self._proc(stdout="")) as mock_run:
            orch._commit_task_completion(task)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert not any("commit" in str(c) for c in calls)

    def test_mensagem_inclui_task_id_e_titulo(self):
        """Mensagem do commit: 'feat: [task-id] título'."""
        orch = self._make_orch()
        task = make_task(id="task-042", title="Adicionar listagem de projetos")

        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout=" M main.py\n"),
            self._proc(returncode=0),
            self._proc(),
            self._proc(returncode=0),
        ]) as mock_run:
            orch._commit_task_completion(task)

        commit_call = next(
            c for c in mock_run.call_args_list
            if c.args[0][1] == "commit"
        )
        msg_arg = " ".join(commit_call.args[0])
        assert "task-042" in msg_arg
        assert "Adicionar listagem de projetos" in msg_arg
        assert "feat:" in msg_arg

    def test_titulo_longo_e_truncado_em_60_chars(self):
        """Títulos longos devem ser truncados em 60 caracteres na mensagem."""
        orch = self._make_orch()
        long_title = "A" * 80
        task = make_task(id="task-001", title=long_title)

        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout=" M file.py\n"),
            self._proc(returncode=0),
            self._proc(),
            self._proc(returncode=0),
        ]) as mock_run:
            orch._commit_task_completion(task)

        commit_call = next(
            c for c in mock_run.call_args_list
            if c.args[0][1] == "commit"
        )
        msg_arg = commit_call.args[0][-1]  # último arg é a mensagem
        assert long_title not in msg_arg
        assert long_title[:60] in msg_arg

    def test_continua_se_commit_falhar(self):
        """Falha no commit (returncode != 0) não deve propagar exceção."""
        orch = self._make_orch()
        task = make_task()

        with patch("squire.subprocess.run", side_effect=[
            self._proc(stdout=" M main.py\n"),
            self._proc(returncode=0),
            self._proc(),
            self._proc(returncode=1, stderr="error: cannot commit"),
        ]):
            orch._commit_task_completion(task)  # não deve lançar

    def test_commit_task_completion_chamado_apos_homolog_ok(self):
        """_commit_task_completion deve ser chamado quando homologação aprova em run()."""
        import sys, types
        orch = make_squire()
        task = make_task()

        commit_mock = orch._commit_task_completion  # já é MagicMock de make_squire

        orch._auto_snapshot_commit = MagicMock()
        orch._run_homologation = MagicMock(return_value=True)
        orch._find_current_task = MagicMock(side_effect=[task, None])
        orch._record_event = MagicMock()
        orch._save_state = MagicMock()

        # progress é importado dinamicamente dentro de run(), não no nível de módulo
        fake_progress = types.ModuleType("progress")
        fake_progress.generate_progress = MagicMock()

        with (
            patch("squire.config.ensure_dirs"),
            patch("squire.ckpt.save_project"),
            patch("squire.ckpt.save_tasks"),
            patch("squire.ckpt.save_history"),
            patch("squire.ckpt.release_lock"),
            patch("squire.ckpt.acquire_lock"),
            patch("squire.threading"),
            patch.dict(sys.modules, {"progress": fake_progress}),
        ):
            orch.run()

        commit_mock.assert_called_once_with(task)

    def test_commit_task_completion_nao_chamado_apos_bloqueio(self):
        """_commit_task_completion NÃO deve ser chamado se a task for bloqueada."""
        orch = make_squire()
        task = make_task()
        commit_mock = orch._commit_task_completion

        orch._auto_snapshot_commit = MagicMock()
        orch._run_homologation = MagicMock(return_value=False)
        orch._find_current_task = MagicMock(side_effect=[task, None])
        orch._record_event = MagicMock()
        orch._save_state = MagicMock()

        with (
            patch("squire.config.ensure_dirs"),
            patch("squire.ckpt.save_project"),
            patch("squire.ckpt.save_tasks"),
            patch("squire.ckpt.save_history"),
            patch("squire.ckpt.release_lock"),
            patch("squire.ckpt.acquire_lock"),
            patch("squire.threading"),
            patch("squire.ckpt.add_alert"),
        ):
            orch.run()

        commit_mock.assert_not_called()


# ── TestPreHomologationChecks ────────────────────────────────────────

class TestPreHomologationChecks:
    """
    _pre_homologation_checks(task) → lista de violations ou [] se tudo ok.
    Usa tmp_path para criar repos temporários e mocks de subprocess para ferramentas
    externas (tsc, go, cargo, zig) que podem não estar instaladas.
    """

    def _make_orch_with_repo(self, tmp_path):
        """Cria Squire com a real _pre_homologation_checks apontando para tmp_path."""
        from squire import Squire
        orch = make_squire()
        # Restaurar o método real (make_squire() o substitui por MagicMock)
        orch._pre_homologation_checks = lambda task: Squire._pre_homologation_checks(orch, task)
        orch.project.repo_path = str(tmp_path)
        return orch

    # ── Universal: arquivo de teste ──────────────────────────────────

    def test_sem_arquivos_relevantes_sem_violations(self, tmp_path):
        """Repo vazio sem tsconfig/go.mod/etc., tdd=False → nenhuma violation."""
        orch = self._make_orch_with_repo(tmp_path)
        task = make_task(tdd=False)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert result == []

    def test_tdd_true_sem_testes_adiciona_violation(self, tmp_path):
        """task.tdd=True mas sem arquivos de teste → violation."""
        orch = self._make_orch_with_repo(tmp_path)
        task = make_task(tdd=True)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert any("teste" in v.lower() or "test" in v.lower() for v in result)

    def test_tdd_true_com_arquivo_de_teste_python(self, tmp_path):
        """task.tdd=True com test_foo.py presente → sem violation de teste."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "test_foo.py").write_text("def test_x(): pass")
        task = make_task(tdd=True)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert not any("test" in v.lower() for v in result)

    def test_tdd_true_com_arquivo_spec_ts(self, tmp_path):
        """task.tdd=True com foo.spec.ts presente (TypeScript) → sem violation de teste."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "tsconfig.json").write_text("{}")
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.spec.ts").write_text("it('works', () => {})")
        task = make_task(tdd=True)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert not any("test" in v.lower() for v in result)

    def test_tdd_ignora_node_modules(self, tmp_path):
        """Arquivos de teste dentro de node_modules não devem contar."""
        orch = self._make_orch_with_repo(tmp_path)
        nm = tmp_path / "node_modules" / "jest"
        nm.mkdir(parents=True)
        (nm / "test_fake.py").write_text("pass")
        task = make_task(tdd=True)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert any("test" in v.lower() for v in result)  # não deve contar node_modules

    # ── Python ───────────────────────────────────────────────────────

    def test_python_syntax_error_adiciona_violation(self, tmp_path):
        """Arquivo .py com syntax error → violation de sintaxe Python."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "bad.py").write_text("def foo(:\n    pass\n")  # syntax error
        task = make_task(tdd=False)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert any("python" in v.lower() or "syntax" in v.lower() for v in result)

    def test_python_sem_syntax_error_sem_violation(self, tmp_path):
        """Arquivo .py válido → sem violation de sintaxe."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "good.py").write_text("def foo():\n    return 42\n")
        task = make_task(tdd=False)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert not any("syntax" in v.lower() for v in result)

    def test_python_type_ignore_no_diff_adiciona_violation(self, tmp_path):
        """'# type: ignore' introduzido no diff → violation."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "main.py").write_text("x: int = 1  # type: ignore\n")
        task = make_task(tdd=False)

        diff_output = "+x: int = 1  # type: ignore\n"
        with patch("squire.subprocess.run", return_value=MagicMock(
            returncode=0, stdout=diff_output, stderr=""
        )):
            result = orch._pre_homologation_checks(task)

        assert any("type: ignore" in v for v in result)

    def test_python_venv_ignorado(self, tmp_path):
        """Arquivos .py dentro de .venv não são verificados para sintaxe."""
        orch = self._make_orch_with_repo(tmp_path)
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "bad_venv.py").write_text("def foo(:\n    pass")  # syntax error em .venv
        task = make_task(tdd=False)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert not any("bad_venv" in v for v in result)

    # ── TypeScript ───────────────────────────────────────────────────

    def test_typescript_tsc_error_adiciona_violation(self, tmp_path):
        """tsc --noEmit retorna código != 0 → violation de TypeScript."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "tsconfig.json").write_text("{}")
        tsc_dir = tmp_path / "node_modules" / ".bin"
        tsc_dir.mkdir(parents=True)
        tsc_bin = tsc_dir / "tsc"
        tsc_bin.write_text("#!/bin/sh\nexit 1")  # tsc "falha"
        tsc_bin.chmod(0o755)
        task = make_task(tdd=False)

        with patch("squire.subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if "--noEmit" in cmd:
                    return MagicMock(returncode=1, stdout="error TS2345: ...", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = side_effect
            result = orch._pre_homologation_checks(task)

        assert any("typescript" in v.lower() or "tsc" in v.lower() for v in result)

    def test_typescript_any_no_diff_adiciona_violation(self, tmp_path):
        """': any' introduzido no diff → violation de tipo TypeScript."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "tsconfig.json").write_text("{}")
        task = make_task(tdd=False)

        diff_output = "+const x: any = foo();\n"
        with patch("squire.subprocess.run", return_value=MagicMock(
            returncode=0, stdout=diff_output, stderr=""
        )):
            result = orch._pre_homologation_checks(task)

        assert any("any" in v for v in result)

    def test_typescript_sem_tsc_instalado_nao_penaliza(self, tmp_path):
        """tsconfig.json presente mas tsc não instalado → sem violation (FileNotFoundError)."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "tsconfig.json").write_text("{}")
        # Não cria node_modules/.bin/tsc → tsc_bin.exists() == False
        task = make_task(tdd=False)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        # sem tsc → só pode ter violation de 'any' se diff tiver 'any'
        assert not any("tsc" in v.lower() for v in result)

    # ── Go ───────────────────────────────────────────────────────────

    def test_go_build_error_adiciona_violation(self, tmp_path):
        """go build retorna erro → violation."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "go.mod").write_text("module example.com/test\ngo 1.21\n")
        task = make_task(tdd=False)

        with patch("squire.subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if cmd[:2] == ["go", "build"]:
                    return MagicMock(returncode=1, stdout="", stderr="build failed")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = side_effect
            result = orch._pre_homologation_checks(task)

        assert any("go" in v.lower() for v in result)

    def test_go_nao_penaliza_se_nao_instalado(self, tmp_path):
        """go.mod presente mas go não instalado → FileNotFoundError → sem violation."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "go.mod").write_text("module example.com/test\ngo 1.21\n")
        task = make_task(tdd=False)

        with patch("squire.subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if cmd[0] == "go":
                    raise FileNotFoundError("go not found")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = side_effect
            result = orch._pre_homologation_checks(task)

        assert not any("go" in v.lower() for v in result)

    # ── Rust ─────────────────────────────────────────────────────────

    def test_rust_cargo_check_error_adiciona_violation(self, tmp_path):
        """cargo check retorna erro → violation de Rust."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        task = make_task(tdd=False)

        with patch("squire.subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if "cargo" in cmd and "check" in cmd:
                    return MagicMock(returncode=1, stdout="error[E0000]: ...", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = side_effect
            result = orch._pre_homologation_checks(task)

        assert any("rust" in v.lower() or "cargo" in v.lower() for v in result)

    def test_rust_unsafe_no_diff_adiciona_violation(self, tmp_path):
        """'unsafe {' introduzido no diff → violation de Rust."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')
        task = make_task(tdd=False)

        diff_output = "+    unsafe { *ptr = 42; }\n"
        with patch("squire.subprocess.run", return_value=MagicMock(
            returncode=0, stdout=diff_output, stderr=""
        )):
            result = orch._pre_homologation_checks(task)

        assert any("unsafe" in v.lower() or "allow" in v.lower() for v in result)

    # ── Zig ──────────────────────────────────────────────────────────

    def test_zig_build_error_adiciona_violation(self, tmp_path):
        """zig build retorna erro → violation de Zig."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "build.zig").write_text("// zig build script")
        task = make_task(tdd=False)

        with patch("squire.subprocess.run") as mock_run:
            def side_effect(cmd, **kwargs):
                if cmd[:2] == ["zig", "build"]:
                    return MagicMock(returncode=1, stdout="", stderr="error: ")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_run.side_effect = side_effect
            result = orch._pre_homologation_checks(task)

        assert any("zig" in v.lower() for v in result)

    def test_zig_catch_unreachable_no_diff_adiciona_violation(self, tmp_path):
        """'catch unreachable' introduzido no diff → violation de Zig."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "build.zig").write_text("// zig build script")
        task = make_task(tdd=False)

        diff_output = "+    const x = foo() catch unreachable;\n"
        with patch("squire.subprocess.run", return_value=MagicMock(
            returncode=0, stdout=diff_output, stderr=""
        )):
            result = orch._pre_homologation_checks(task)

        assert any("unreachable" in v.lower() or "_ =" in v for v in result)

    # ── Retorna lista vazia se tudo ok ───────────────────────────────

    def test_retorna_lista_vazia_se_tudo_ok(self, tmp_path):
        """Todas as verificações passam → retorna []."""
        orch = self._make_orch_with_repo(tmp_path)
        (tmp_path / "main.py").write_text("def ok(): return 1\n")
        (tmp_path / "test_main.py").write_text("def test_ok(): assert ok() == 1\n")
        task = make_task(tdd=True)

        with patch("squire.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
            result = orch._pre_homologation_checks(task)

        assert result == []


# ── TestGatePreHomologation ──────────────────────────────────────────

class TestGatePreHomologation:
    """
    O gate pré-homologação em _run_homologation bloqueia chamadas ao Claude Code
    quando há violations mecânicas, com cap de 2 falhas consecutivas.
    """

    def test_gate_bloqueia_cc_quando_ha_violations(self):
        """Violations → homologator.review NÃO chamado, inner loop roda mais uma vez."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=3)
        orch._run_inner_loop = MagicMock(return_value=True)
        # Primeira chamada do gate: violation. Segunda: limpo. Terceira: aprovação.
        orch._pre_homologation_checks.side_effect = [
            ["TypeScript error: TS2345"],  # gate falha → não gasta CC
            [],                             # gate passa → CC chamado
        ]
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            result = orch._run_homologation(task)

        assert result is True
        # CC chamado apenas uma vez (após o gate passar)
        orch.homologator.review.assert_called_once()
        # Inner loop chamado 2x: uma para a rodada com gate, uma para a rodada limpa
        assert orch._run_inner_loop.call_count == 2

    def test_gate_permite_cc_sem_violations(self):
        """Sem violations → homologator.review chamado normalmente."""
        orch = make_squire()
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch._pre_homologation_checks.return_value = []
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        orch.homologator.review.assert_called_once()

    def test_gate_cap_2_falhas_passa_adiante(self):
        """Após 2 gate failures consecutivos, CC é chamado mesmo com violations."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=5)
        orch._run_inner_loop = MagicMock(return_value=True)
        # Gate sempre falha → após 2 consecutivos, CC é chamado
        orch._pre_homologation_checks.return_value = ["violation persistente"]
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        # CC deve ser chamado apesar das violations (cap atingido)
        orch.homologator.review.assert_called_once()

    def test_violations_aparecem_como_feedback_no_inner_loop(self):
        """Texto das violations deve aparecer no homologation_feedback da próxima rodada."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=3, tdd=False)

        inner_feedbacks = []

        def capture_inner(t, homologation_feedback="", test_hashes=None):
            inner_feedbacks.append(homologation_feedback)
            return True

        orch._run_inner_loop = capture_inner
        orch._pre_homologation_checks.side_effect = [
            ["TypeScript errors (tsc --noEmit):\nerror TS2345"],
            [],
        ]
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        # A segunda chamada ao inner loop deve conter o texto da violation
        assert len(inner_feedbacks) >= 2
        assert "TypeScript" in inner_feedbacks[1] or "TS2345" in inner_feedbacks[1]

    def test_gate_nao_roda_em_dry_run(self):
        """Em dry_run=True, o gate não é chamado."""
        orch = make_squire()
        orch.dry_run = True
        task = make_task()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        orch._pre_homologation_checks.assert_not_called()

    def test_gate_failures_resetado_apos_passar(self):
        """gate_failures deve ser zerado quando o gate passa (violation seguida de clean)."""
        orch = make_squire()
        task = make_task(max_homologation_attempts=4, tdd=False)
        orch._run_inner_loop = MagicMock(return_value=True)
        # Padrão: violation → clean → violation → clean → aprovação
        orch._pre_homologation_checks.side_effect = [
            ["erro 1"],   # falha
            [],           # passa (reset gate_failures → 0)
            ["erro 2"],   # falha novamente (não ultrapassa cap pois foi resetado)
            [],           # passa
        ]
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="ruim"),
            make_homolog_result(approved=True),
        ]

        with patch("squire.time"):
            result = orch._run_homologation(task)

        assert result is True
        # CC chamado 2x (após cada gate pass)
        assert orch.homologator.review.call_count == 2


# ── TestProgressTxtAfterTask ─────────────────────────────────────────

class TestProgressTxtAfterTask:
    """
    progress.generate_progress(project_id) deve ser chamado após cada task
    concluída com sucesso (padrão Ralph Loop — memória entre tasks).

    progress é importado dinamicamente dentro de run() com 'import progress as _progress',
    então é mockado via patch.dict(sys.modules, ...).
    """

    def _run_with_fake_progress(self, orch, task, homolog_ok, fail_progress=False):
        """Helper: roda orch.run() com progress mockado. Retorna o mock."""
        import sys, types
        fake_progress = types.ModuleType("progress")
        fake_progress.generate_progress = MagicMock()
        if fail_progress:
            fake_progress.generate_progress.side_effect = RuntimeError("disco cheio")

        orch._auto_snapshot_commit = MagicMock()
        orch._run_homologation = MagicMock(return_value=homolog_ok)
        orch._find_current_task = MagicMock(side_effect=[task, None])
        orch._record_event = MagicMock()
        orch._save_state = MagicMock()

        patches = [
            patch("squire.config.ensure_dirs"),
            patch("squire.ckpt.save_project"),
            patch("squire.ckpt.save_tasks"),
            patch("squire.ckpt.save_history"),
            patch("squire.ckpt.release_lock"),
            patch("squire.ckpt.acquire_lock"),
            patch("squire.threading"),
            patch.dict(sys.modules, {"progress": fake_progress}),
        ]
        if not homolog_ok:
            patches.append(patch("squire.ckpt.add_alert"))

        for p in patches:
            p.start()
        try:
            orch.run()
        finally:
            for p in reversed(patches):
                p.stop()

        return fake_progress.generate_progress

    def test_generate_progress_chamado_apos_task_concluida(self):
        """Após homolog_ok, generate_progress é chamado com o project_id correto."""
        orch = make_squire()
        task = make_task()
        mock_gp = self._run_with_fake_progress(orch, task, homolog_ok=True)
        mock_gp.assert_called_once_with(orch.project_id)

    def test_generate_progress_nao_chamado_quando_task_bloqueada(self):
        """Se a task é bloqueada (homolog_ok=False), generate_progress NÃO é chamado."""
        orch = make_squire()
        task = make_task()
        mock_gp = self._run_with_fake_progress(orch, task, homolog_ok=False)
        mock_gp.assert_not_called()

    def test_generate_progress_erro_nao_aborta_task(self):
        """Exceção em generate_progress não deve impedir que a task seja marcada como concluída."""
        orch = make_squire()
        task = make_task()
        self._run_with_fake_progress(orch, task, homolog_ok=True, fail_progress=True)
        from models import TaskStatus
        assert task.status == TaskStatus.completed


# ── TestEffortLowEscalation ──────────────────────────────────────────

class TestEffortLowEscalation:
    """
    Para tasks effort:low, após 2 rejeições consecutivas com loop detectado,
    Claude Code implementa diretamente sem esperar a penúltima rodada.
    """

    def _make_looping_task(self, effort="low", **kwargs) -> "Task":
        """Cria task com rejection_summaries configuradas para acionar _is_looping."""
        # _is_looping requer LOOP_DETECT_THRESHOLD summaries com 4+ palavras em comum
        loop_summary = "componente GlobalStats typescript erro tipo importação"
        task = make_task(
            effort=effort,
            homologation_attempt=2,
            max_homologation_attempts=5,
            rejection_summaries=[loop_summary] * 4,
            **kwargs,
        )
        return task

    def test_effort_low_aciona_escalacao_antecipada(self):
        """effort:low + 2 rejeições + loop → implement_directly chamado."""
        orch = make_squire()
        task = self._make_looping_task(effort="low")
        orch._run_inner_loop = MagicMock(return_value=False)
        orch._pre_homologation_checks.return_value = []
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="ainda não"
        )
        orch.escalation.implement_directly = MagicMock(return_value=(["src/foo.ts"], None))

        with patch("squire.time"):
            orch._run_homologation(task)

        orch.escalation.implement_directly.assert_called()

    def test_effort_medium_nao_aciona_escalacao_antecipada(self):
        """effort:medium, mesmas condições → implement_directly NÃO chamado na 3ª rodada.
        Usa max_homologation_attempts grande para não atingir a condição de penúltima rodada."""
        orch = make_squire()
        # attempt=0, max=20: loop dispara em attempt=3 (com 4 rejeições idênticas)
        # mas is_early_escalation falha pois effort != low
        # is_penultimate requer attempt >= max-1=19, não chegamos lá neste teste
        loop_summary = "componente GlobalStats typescript erro tipo importação"
        task = make_task(
            effort="medium",
            homologation_attempt=0,
            max_homologation_attempts=20,
            rejection_summaries=[loop_summary] * 4,
        )
        orch._run_inner_loop = MagicMock(return_value=False)
        orch._pre_homologation_checks.return_value = []
        # Rejeita 3x para acionar loop detection, depois aprova
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback=loop_summary),
            make_homolog_result(approved=False, feedback=loop_summary),
            make_homolog_result(approved=False, feedback=loop_summary),
            make_homolog_result(approved=True),
        ]
        orch.escalation.implement_directly = MagicMock(return_value=([], None))

        with patch("squire.time"):
            orch._run_homologation(task)

        orch.escalation.implement_directly.assert_not_called()

    def test_dry_run_nao_aciona_escalacao(self):
        """dry_run=True → is_early_escalation não aciona mesmo com effort:low + loop."""
        orch = make_squire()
        orch.dry_run = True
        task = self._make_looping_task(effort="low")
        orch._run_inner_loop = MagicMock(return_value=False)
        orch._pre_homologation_checks.return_value = []
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="ainda não"
        )
        orch.escalation.implement_directly = MagicMock(return_value=([], None))

        with patch("squire.time"):
            orch._run_homologation(task)

        orch.escalation.implement_directly.assert_not_called()

    def test_escalacao_requer_loop_detectado(self):
        """effort:low + 2 rejeições mas SEM loop → implement_directly NÃO chamado."""
        orch = make_squire()
        # Task sem rejection_summaries repetidas → não aciona _is_looping
        task = make_task(
            effort="low",
            homologation_attempt=2,
            max_homologation_attempts=5,
            rejection_summaries=["erro tipo A", "problema diferente B", "falha outro C"],
        )
        orch._run_inner_loop = MagicMock(return_value=False)
        orch._pre_homologation_checks.return_value = []
        orch.homologator.review.return_value = make_homolog_result(
            approved=False, feedback="ainda não"
        )
        orch.escalation.implement_directly = MagicMock(return_value=([], None))

        with patch("squire.time"):
            orch._run_homologation(task)

        orch.escalation.implement_directly.assert_not_called()

    def test_escalacao_marca_claude_code_assisted(self):
        """Quando implement_directly é chamado, task.claude_code_assisted deve ser True."""
        orch = make_squire()
        task = self._make_looping_task(effort="low")
        task.claude_code_assisted = False
        orch._run_inner_loop = MagicMock(return_value=False)
        orch._pre_homologation_checks.return_value = []
        # Precisa rejeitar primeiro para que is_early_escalation dispare (o bloco fica após
        # o review retornar rejected — se approved imediatamente, retorna True antes da escalação)
        orch.homologator.review.side_effect = [
            make_homolog_result(approved=False, feedback="ainda com erro"),
            make_homolog_result(approved=True),
        ]
        orch.escalation.implement_directly = MagicMock(return_value=(["src/GlobalStats.tsx"], None))

        with patch("squire.time"):
            orch._run_homologation(task)

        assert task.claude_code_assisted is True


# ── TestRedPhase ──────────────────────────────────────────────────────

class TestRedPhase:
    """Gap 8: fase RED — escrever testes antes da implementação."""

    def test_red_phase_nao_roda_com_tdd_false(self):
        """Com tdd=False, _run_red_phase não deve ser chamado."""
        orch = make_squire()
        task = make_task(tdd=False)
        orch._run_red_phase = MagicMock()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)
        orch.inner_loop.snapshot_test_hashes.return_value = {}

        with patch("squire.time"):
            orch._run_homologation(task)

        orch._run_red_phase.assert_not_called()

    def test_red_phase_roda_quando_sem_testes_existentes(self):
        """Com tdd=True e sem testes, _run_red_phase deve ser chamado."""
        orch = make_squire()
        task = make_task(tdd=True)
        orch._run_red_phase = MagicMock()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)
        # Primeiro snapshot: vazio (nenhum teste existente) → RED phase deve rodar
        # Segundo snapshot: após RED phase → retorna hashes
        orch.inner_loop.snapshot_test_hashes.side_effect = [
            {},                                          # antes da RED phase
            {"tests/test_foo.py": "abc123"},             # após RED phase
        ]

        with patch("squire.time"):
            orch._run_homologation(task)

        orch._run_red_phase.assert_called_once_with(task)

    def test_red_phase_nao_roda_quando_testes_existem(self):
        """Com tdd=True mas testes já existentes, _run_red_phase NÃO deve rodar."""
        orch = make_squire()
        task = make_task(tdd=True)
        orch._run_red_phase = MagicMock()
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)
        orch.inner_loop.snapshot_test_hashes.return_value = {"tests/test_existing.py": "hash1"}

        with patch("squire.time"):
            orch._run_homologation(task)

        orch._run_red_phase.assert_not_called()

    def test_test_hashes_passados_ao_inner_loop(self):
        """test_hashes do snapshot devem ser passados ao _run_inner_loop."""
        orch = make_squire()
        task = make_task(tdd=True)
        hashes = {"tests/test_core.py": "deadbeef"}
        orch._run_red_phase = MagicMock()
        orch.inner_loop.snapshot_test_hashes.side_effect = [{}, hashes]

        inner_loop_calls = []

        def capture(t, homologation_feedback="", test_hashes=None):
            inner_loop_calls.append(test_hashes)
            return True

        orch._run_inner_loop = capture
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        assert inner_loop_calls[0] == hashes

    def test_test_hashes_passados_ao_homologador(self):
        """test_hashes devem ser passados ao homologator.review."""
        orch = make_squire()
        task = make_task(tdd=True)
        hashes = {"tests/test_api.py": "cafebabe"}
        orch._run_red_phase = MagicMock()
        orch.inner_loop.snapshot_test_hashes.side_effect = [{}, hashes]
        orch._run_inner_loop = MagicMock(return_value=True)
        orch.homologator.review.return_value = make_homolog_result(approved=True)

        with patch("squire.time"):
            orch._run_homologation(task)

        call_kwargs = orch.homologator.review.call_args[1]
        assert call_kwargs.get("test_hashes") == hashes

    def test_dry_run_pula_red_phase_real(self):
        """Em dry_run, _run_red_phase não deve invocar subprocess."""
        orch = make_squire()
        orch.dry_run = True
        task = make_task(tdd=True)

        with patch("squire.subprocess.run") as mock_sub:
            orch._run_red_phase(task)

        mock_sub.assert_not_called()
