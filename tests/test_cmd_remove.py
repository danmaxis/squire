"""Testes para o comando 'squire rm <project-id>'."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────

def run_cmd_remove(project_id: str, user_input: str, tmp_state: Path):
    """
    Executa cmd_remove com STATE_ROOT apontando para tmp_state.
    Simula o input do usuário via stdin mockado.
    Retorna o código de saída (via SystemExit) ou None se concluiu sem exit.
    """
    from squire import cmd_remove

    with (
        patch.dict("os.environ", {"SQUIRE_STATE_ROOT": str(tmp_state)}),
        patch("squire.config.STATE_ROOT", tmp_state),
        patch("squire.config.PROJECTS_DIR", tmp_state / "projects"),
        patch("squire.config.project_dir", lambda pid: tmp_state / "projects" / pid),
        patch("squire.ckpt.load_project", return_value=None),
        patch("builtins.input", return_value=user_input),
    ):
        try:
            cmd_remove(project_id)
            return None
        except SystemExit as e:
            return e.code


def _make_project_dir(tmp_state: Path, project_id: str) -> Path:
    """Cria diretório de estado de projeto com arquivos simulados."""
    project_dir = tmp_state / "projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text('{"id": "' + project_id + '"}')
    (project_dir / "tasks.json").write_text('{"tasks": []}')
    (project_dir / "history.json").write_text('{"events": []}')
    return project_dir


# ── TestCmdRemoveConfirmation ─────────────────────────────────────────

class TestCmdRemoveConfirmation:
    """Fluxo de confirmação: a frase correta deve deletar, a errada deve abortar."""

    def test_confirmacao_correta_deleta_diretorio(self, tmp_path):
        """Digite '<project_id> <word>' correto → diretório removido."""
        project_dir = _make_project_dir(tmp_path, "meu-projeto")
        assert project_dir.exists()

        # Mockar random.choice para retornar palavra conhecida
        with patch("squire.random.choice", return_value="bravo"):
            exit_code = run_cmd_remove("meu-projeto", "meu-projeto bravo", tmp_path)

        assert exit_code is None  # concluiu sem sys.exit
        assert not project_dir.exists()

    def test_confirmacao_errada_nao_deleta(self, tmp_path):
        """Digite frase errada → diretório preservado, exit(1)."""
        project_dir = _make_project_dir(tmp_path, "meu-projeto")

        with patch("squire.random.choice", return_value="bravo"):
            exit_code = run_cmd_remove("meu-projeto", "meu-projeto errado", tmp_path)

        assert exit_code == 1
        assert project_dir.exists()

    def test_confirmacao_so_com_nome_nao_deleta(self, tmp_path):
        """Digitar só o nome do projeto (sem a palavra aleatória) → rejeitado."""
        project_dir = _make_project_dir(tmp_path, "meu-projeto")

        with patch("squire.random.choice", return_value="sierra"):
            exit_code = run_cmd_remove("meu-projeto", "meu-projeto", tmp_path)

        assert exit_code == 1
        assert project_dir.exists()

    def test_confirmacao_so_palavra_nao_deleta(self, tmp_path):
        """Digitar só a palavra aleatória (sem o nome) → rejeitado."""
        project_dir = _make_project_dir(tmp_path, "meu-projeto")

        with patch("squire.random.choice", return_value="tango"):
            exit_code = run_cmd_remove("meu-projeto", "tango", tmp_path)

        assert exit_code == 1
        assert project_dir.exists()

    def test_confirmacao_ordem_invertida_nao_deleta(self, tmp_path):
        """'<word> <project_id>' (ordem invertida) → rejeitado."""
        project_dir = _make_project_dir(tmp_path, "meu-projeto")

        with patch("squire.random.choice", return_value="oscar"):
            exit_code = run_cmd_remove("meu-projeto", "oscar meu-projeto", tmp_path)

        assert exit_code == 1
        assert project_dir.exists()

    def test_confirmacao_vazia_nao_deleta(self, tmp_path):
        """Enter vazio → rejeitado."""
        project_dir = _make_project_dir(tmp_path, "proj")

        with patch("squire.random.choice", return_value="lima"):
            exit_code = run_cmd_remove("proj", "", tmp_path)

        assert exit_code == 1
        assert project_dir.exists()

    def test_ctrl_c_nao_deleta(self, tmp_path):
        """KeyboardInterrupt (Ctrl+C) → exit(0) sem deletar."""
        project_dir = _make_project_dir(tmp_path, "proj")

        with (
            patch("squire.random.choice", return_value="zulu"),
            patch("squire.config.project_dir", lambda pid: tmp_path / "projects" / pid),
            patch("squire.ckpt.load_project", return_value=None),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            from squire import cmd_remove
            with patch("squire.config.PROJECTS_DIR", tmp_path / "projects"):
                try:
                    cmd_remove("proj")
                    exit_code = None
                except SystemExit as e:
                    exit_code = e.code

        assert exit_code == 0
        assert project_dir.exists()


# ── TestCmdRemoveProjectNotFound ─────────────────────────────────────

class TestCmdRemoveProjectNotFound:
    """Projeto inexistente deve abortar com exit(1) sem perguntar confirmação."""

    def test_projeto_inexistente_exit_1(self, tmp_path):
        """Projeto que não existe → exit(1) imediato."""
        (tmp_path / "projects").mkdir(parents=True)

        with (
            patch("squire.config.project_dir", lambda pid: tmp_path / "projects" / pid),
            patch("squire.config.PROJECTS_DIR", tmp_path / "projects"),
            patch("squire.ckpt.load_project", return_value=None),
            patch("builtins.input") as mock_input,
        ):
            from squire import cmd_remove
            try:
                cmd_remove("projeto-fantasma")
                exit_code = None
            except SystemExit as e:
                exit_code = e.code

        assert exit_code == 1
        mock_input.assert_not_called()  # não deve pedir confirmação


# ── TestCmdRemoveDeletsOnlyState ─────────────────────────────────────

class TestCmdRemoveDeletsOnlyState:
    """Apenas o diretório de estado é removido — o repo_path não é tocado."""

    def test_apenas_state_dir_e_removido(self, tmp_path):
        """O repo_path listado em project.json não deve ser apagado."""
        project_dir = _make_project_dir(tmp_path, "proj")

        # Simular um repo_path em outro lugar
        fake_repo = tmp_path / "repo" / "proj"
        fake_repo.mkdir(parents=True)
        (fake_repo / "src").mkdir()

        fake_project = MagicMock()
        fake_project.repo_path = str(fake_repo)

        with (
            patch("squire.random.choice", return_value="golf"),
            patch("squire.config.project_dir", lambda pid: tmp_path / "projects" / pid),
            patch("squire.config.PROJECTS_DIR", tmp_path / "projects"),
            patch("squire.ckpt.load_project", return_value=fake_project),
            patch("builtins.input", return_value="proj golf"),
        ):
            from squire import cmd_remove
            try:
                cmd_remove("proj")
            except SystemExit:
                pass

        assert not project_dir.exists()  # estado removido
        assert fake_repo.exists()         # repositório de código intacto

    def test_todos_arquivos_de_estado_removidos(self, tmp_path):
        """Todos os JSONs do diretório de estado são deletados."""
        project_dir = _make_project_dir(tmp_path, "proj")
        extra_file = project_dir / "checkpoint.json"
        extra_file.write_text("{}")

        with patch("squire.random.choice", return_value="mike"):
            run_cmd_remove("proj", "proj mike", tmp_path)

        assert not project_dir.exists()


# ── TestCmdRemoveMainDispatch ─────────────────────────────────────────

class TestCmdRemoveMainDispatch:
    """main() detecta 'rm' como primeiro arg e despacha para cmd_remove."""

    def test_main_rm_chama_cmd_remove(self, tmp_path):
        """'squire rm proj' → cmd_remove('proj') é chamado."""
        with (
            patch.object(sys, "argv", ["squire.py", "rm", "proj"]),
            patch("squire.cmd_remove") as mock_rm,
        ):
            from squire import main
            main()

        mock_rm.assert_called_once_with("proj")

    def test_main_rm_sem_projeto_exit_1(self, tmp_path):
        """'squire rm' sem project_id → exit(1)."""
        with patch.object(sys, "argv", ["squire.py", "rm"]):
            from squire import main
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1

    def test_main_sem_rm_nao_chama_cmd_remove(self):
        """'squire proj' sem 'rm' → cmd_remove não é chamado."""
        with (
            patch.object(sys, "argv", ["squire.py", "my-proj"]),
            patch("squire.cmd_remove") as mock_rm,
            patch("squire.Squire") as mock_squire,
        ):
            mock_squire.return_value.run = MagicMock()
            from squire import main
            main()

        mock_rm.assert_not_called()
