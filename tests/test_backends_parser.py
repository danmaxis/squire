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
