"""Testes unitários para homologator.py — foco na filtragem de arquivos e limites de prompt."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from homologator import Homologator


def make_homologator(tmp_path: Path) -> Homologator:
    return Homologator(project_path=str(tmp_path), claude_bin="claude", verbose=False)


# ── TestGitFallbackFiles ─────────────────────────────────────────────

class TestGitFallbackFiles:
    """_git_fallback_files deve filtrar node_modules/dist e retornar só arquivos fonte."""

    def _proc(self, stdout="", returncode=0):
        p = MagicMock()
        p.returncode = returncode
        p.stdout = stdout
        p.stderr = ""
        return p

    def test_filtra_node_modules(self, tmp_path):
        h = make_homologator(tmp_path)
        ls_output = "src/index.ts\nnode_modules/.bin/tsc\nnode_modules/typescript/ts.js\npackage.json\n"
        with patch("homologator.subprocess.run", side_effect=[
            self._proc(""),          # git diff HEAD
            self._proc(""),          # git diff --cached HEAD
            self._proc(ls_output),   # git ls-files
        ]):
            files = h._git_fallback_files()

        assert "src/index.ts" in files
        assert "package.json" in files
        assert not any("node_modules" in f for f in files)

    def test_filtra_dist(self, tmp_path):
        h = make_homologator(tmp_path)
        ls_output = "src/bing.ts\ndist/bing.js\ndist/bing.d.ts\n"
        with patch("homologator.subprocess.run", side_effect=[
            self._proc(""),
            self._proc(""),
            self._proc(ls_output),
        ]):
            files = h._git_fallback_files()

        assert "src/bing.ts" in files
        assert not any("dist" in f for f in files)

    def test_repo_sem_commits_retorna_apenas_fontes(self, tmp_path):
        """git diff falha (sem HEAD) mas ls-files retorna node_modules — deve filtrar."""
        h = make_homologator(tmp_path)
        all_untracked = (
            "src/index.ts\npackage.json\ntsconfig.json\n"
            "node_modules/.bin/acorn\nnode_modules/typescript/README.md\n"
            "dist/index.js\n"
        )
        with patch("homologator.subprocess.run", side_effect=[
            self._proc("", returncode=128),
            self._proc("", returncode=128),
            self._proc(all_untracked),
        ]):
            files = h._git_fallback_files()

        assert set(files) == {"src/index.ts", "package.json", "tsconfig.json"}

    def test_retorna_vazio_em_excecao(self, tmp_path):
        h = make_homologator(tmp_path)
        with patch("homologator.subprocess.run", side_effect=Exception("git não encontrado")):
            files = h._git_fallback_files()
        assert files == []


# ── TestReadFilesForReview ───────────────────────────────────────────

class TestReadFilesForReview:
    """_read_files_for_review — limites de arquivos e conteúdo para não inflar o prompt."""

    def test_le_arquivo_existente(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("const x = 1;\n")
        h = make_homologator(tmp_path)
        result = h._read_files_for_review(["src/index.ts"])
        assert "src/index.ts" in result
        assert "const x = 1;" in result

    def test_retorna_mensagem_sem_arquivos(self, tmp_path):
        h = make_homologator(tmp_path)
        # Sem files_touched e sem git → fallbacks retornam vazio
        with patch.object(h, "_git_fallback_files", return_value=[]), \
             patch.object(h, "_recent_code_files", return_value=[]):
            result = h._read_files_for_review([])
        assert "Nenhum arquivo" in result

    def test_cap_maximo_de_arquivos(self, tmp_path):
        """Mais de 20 arquivos passados → só os 20 primeiros são lidos."""
        h = make_homologator(tmp_path)
        # Criar 25 arquivos de código
        (tmp_path / "src").mkdir()
        files = []
        for i in range(25):
            p = tmp_path / "src" / f"file{i:02d}.ts"
            p.write_text(f"// file {i}\n")
            files.append(f"src/file{i:02d}.ts")

        result = h._read_files_for_review(files)

        # Só os primeiros 20 devem aparecer
        included = [f for f in files if f in result]
        assert len(included) <= 20

    def test_cap_tamanho_conteudo(self, tmp_path):
        """Conteúdo total acima de 80KB deve ser truncado."""
        h = make_homologator(tmp_path)
        (tmp_path / "src").mkdir()
        # Criar 5 arquivos de 25KB cada (total 125KB > limite de 80KB)
        files = []
        for i in range(5):
            p = tmp_path / "src" / f"big{i}.ts"
            p.write_text("x" * 25_000)
            files.append(f"src/big{i}.ts")

        result = h._read_files_for_review(files)

        assert "truncado" in result
        # Conteúdo deve estar bem abaixo de 125KB
        assert len(result.encode("utf-8")) < 120_000

    def test_usa_fallback_quando_files_touched_vazio(self, tmp_path):
        """Sem files_touched → chama _git_fallback_files."""
        h = make_homologator(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export {}")

        with patch.object(h, "_git_fallback_files", return_value=["src/app.ts"]) as mock_fb, \
             patch.object(h, "_recent_code_files", return_value=[]):
            result = h._read_files_for_review([])

        mock_fb.assert_called_once()
        assert "src/app.ts" in result

    def test_usa_recent_files_quando_git_vazio(self, tmp_path):
        """_git_fallback retorna [] → chama _recent_code_files."""
        h = make_homologator(tmp_path)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export {}")

        with patch.object(h, "_git_fallback_files", return_value=[]), \
             patch.object(h, "_recent_code_files", return_value=["src/app.ts"]) as mock_rc:
            result = h._read_files_for_review([])

        mock_rc.assert_called_once()
        assert "src/app.ts" in result

    def test_arquivo_inexistente_nao_quebra(self, tmp_path):
        """Arquivo listado mas não existente → mensagem de erro no resultado, não exceção."""
        h = make_homologator(tmp_path)
        result = h._read_files_for_review(["src/nao_existe.ts"])
        assert "nao_existe.ts" in result
        assert "erro ao ler" in result
