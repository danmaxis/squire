"""Testes unitários para o parser de output do LiteLLMBackend."""
from __future__ import annotations

from pathlib import Path

import pytest

from backends import LiteLLMBackend


@pytest.fixture
def backend(tmp_path):
    b = LiteLLMBackend()
    return b, tmp_path


class TestExtractFilepath:
    def setup_method(self):
        self.b = LiteLLMBackend()

    def test_filepath_prefixo(self):
        assert self.b._extract_filepath("filepath:src/foo.ts") == "src/foo.ts"

    def test_linguagem_e_caminho(self):
        assert self.b._extract_filepath("typescript:src/lib/types.ts") == "src/lib/types.ts"

    def test_caminho_direto(self):
        assert self.b._extract_filepath("src/components/Card.tsx") == "src/components/Card.tsx"

    def test_trailing_colon(self):
        """Formato Qwen: caminho com dois-pontos no final."""
        assert self.b._extract_filepath("src/hooks/useAutoRefresh.ts:") == "src/hooks/useAutoRefresh.ts"

    def test_trailing_colon_com_linguagem(self):
        assert self.b._extract_filepath("typescript:src/foo.ts:") == "src/foo.ts"

    def test_dockerfile(self):
        assert self.b._extract_filepath("Dockerfile") == "Dockerfile"

    def test_makefile(self):
        assert self.b._extract_filepath("Makefile") == "Makefile"

    def test_dockerignore(self):
        assert self.b._extract_filepath(".dockerignore") == ".dockerignore"

    def test_arquivo_com_ponto(self):
        assert self.b._extract_filepath("docker-compose.yml") == "docker-compose.yml"

    def test_linguagem_sem_caminho_retorna_none(self):
        assert self.b._extract_filepath("typescript") is None

    def test_vazio_retorna_none(self):
        assert self.b._extract_filepath("") is None

    def test_none_retorna_none(self):
        assert self.b._extract_filepath(None) is None

    def test_apenas_pontos_retorna_none(self):
        assert self.b._extract_filepath(":") is None


class TestApplyChanges:
    def test_formato_filepath_prefixo(self, tmp_path):
        b = LiteLLMBackend()
        response = "```filepath:src/foo.ts\nconst x = 1;\n```"
        files = b._apply_changes(response, tmp_path)
        assert files == ["src/foo.ts"]
        assert (tmp_path / "src/foo.ts").read_text() == "const x = 1;"

    def test_formato_linguagem_colon_caminho(self, tmp_path):
        b = LiteLLMBackend()
        response = "```typescript:src/lib/types.ts\nexport type Foo = string;\n```"
        files = b._apply_changes(response, tmp_path)
        assert files == ["src/lib/types.ts"]
        assert "export type Foo" in (tmp_path / "src/lib/types.ts").read_text()

    def test_formato_path_antes_do_fence(self, tmp_path):
        """Formato Qwen: caminho na linha antes do fence."""
        b = LiteLLMBackend()
        response = "src/components/Card.tsx:\n```tsx\nimport React from 'react';\n```"
        files = b._apply_changes(response, tmp_path)
        assert files == ["src/components/Card.tsx"]

    def test_formato_path_trailing_colon(self, tmp_path):
        """Formato Qwen com dois-pontos no final do caminho."""
        b = LiteLLMBackend()
        response = "src/hooks/useRefresh.ts:\n```typescript\nconst hook = () => {};\n```"
        files = b._apply_changes(response, tmp_path)
        assert "src/hooks/useRefresh.ts" in files
        assert (tmp_path / "src/hooks/useRefresh.ts").exists()

    def test_multiplos_arquivos(self, tmp_path):
        b = LiteLLMBackend()
        response = (
            "```filepath:src/a.ts\nconst a = 1;\n```\n"
            "```filepath:src/b.ts\nconst b = 2;\n```"
        )
        files = b._apply_changes(response, tmp_path)
        assert "src/a.ts" in files
        assert "src/b.ts" in files

    def test_cria_diretorios_intermediarios(self, tmp_path):
        b = LiteLLMBackend()
        response = "```filepath:src/deep/nested/file.ts\nexport {};\n```"
        b._apply_changes(response, tmp_path)
        assert (tmp_path / "src/deep/nested/file.ts").exists()

    def test_sem_arquivo_identificado_retorna_vazio(self, tmp_path):
        b = LiteLLMBackend()
        response = "```typescript\nconst x = 1;\n```"
        files = b._apply_changes(response, tmp_path)
        assert files == []

    def test_dockerfile_sem_extensao(self, tmp_path):
        b = LiteLLMBackend()
        response = "Dockerfile\n```\nFROM node:20-alpine\nRUN echo ok\n```"
        files = b._apply_changes(response, tmp_path)
        assert "Dockerfile" in files
        assert (tmp_path / "Dockerfile").exists()


# ── Validação de caminhos (lixo do Qwen fora dos fences) ─────────────

class TestPlausibleRelpath:
    """_is_plausible_relpath rejeita o lixo observado em produção."""

    @pytest.mark.parametrize("junk", [
        "# src",            # comentário markdown
        '# tests',
        'rm -rf "',         # linha de shell
        "pytest==8.0.0",    # linha de requirements
        "return a ",        # linha de código
        "where = [\".\"]",  # linha de toml
        "../../etc/passwd", # traversal
        "/abs/path.py",     # absoluto
        "a/../b.py",        # traversal embutido
        "src/",             # termina em barra (segmento vazio)
        "src",              # diretório sem extensão
        "foo.",             # extensão vazia
        "-rf.py",           # começa com hífen
        "a" * 201 + ".py",  # longo demais
        "",
    ])
    def test_rejeita_lixo(self, junk):
        from backends import _is_plausible_relpath
        assert _is_plausible_relpath(junk) is False

    @pytest.mark.parametrize("good", [
        "src/foo.ts",
        "hello.py",
        "a/b/c.py",
        "Dockerfile",
        "Makefile",
        ".dockerignore",
        ".gitignore",
        "src/components/Foo-Bar.tsx",
        "pkg/@scope/index.d.ts",
        "docs/README.md",
    ])
    def test_aceita_caminhos_legitimos(self, good):
        from backends import _is_plausible_relpath
        assert _is_plausible_relpath(good) is True


class TestApplyChangesJunkProtection:
    def test_lixo_nao_vira_arquivo(self, tmp_path, capsys):
        from backends import LiteLLMBackend
        b = LiteLLMBackend(model="m", base_url="http://x", api_key="k")
        response = (
            "Aqui está:\n"
            "pytest==8.0.0\n"
            "```\n"
            "flask==3.0.0\n"
            "```\n"
            "```filepath:src/app.py\n"
            "print('ok')\n"
            "```\n"
        )
        touched = b._apply_changes(response, tmp_path)
        assert touched == ["src/app.py"]
        assert (tmp_path / "src" / "app.py").read_text() == "print('ok')"
        assert not (tmp_path / "pytest==8.0.0").exists()

    def test_traversal_e_bloqueado_na_escrita(self, tmp_path):
        from backends import LiteLLMBackend
        b = LiteLLMBackend(model="m", base_url="http://x", api_key="k")
        with pytest.raises(ValueError):
            b._write_file(tmp_path, "../fora.py", "x")
