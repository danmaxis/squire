"""
Padrão Viking — governança de contexto por domínio.

Cada projeto pode ter um diretório /docs/viking/ com arquivos Markdown
que definem restrições por domínio técnico (stack, banco de dados, etc.).
O Validador (Claude) injeta esses arquivos antes de delegar ao Executor (LLM local),
garantindo que as regras do projeto sejam respeitadas.

Estrutura esperada no repo do projeto:
    docs/viking/
    ├── stack_python.md     — regras de linting, tipagem, estilo
    ├── banco_dados.md      — padrões SQL, proibições, migrações
    └── (outros domínios)
"""

from __future__ import annotations

from pathlib import Path


VIKING_DIR = "docs/viking"


def load_viking_context(
    project_repo_path: Path,
    domain: str | None = None,
    max_chars: int = 3000,
) -> str:
    """
    Lê os arquivos /docs/viking/*.md do projeto e retorna como bloco de texto.

    Args:
        project_repo_path: Caminho raiz do repositório do projeto.
        domain: Se fornecido, carrega apenas o arquivo com esse nome (sem .md).
                Se None, carrega todos os arquivos Viking.
        max_chars: Limite total de caracteres para evitar overflow de contexto.

    Returns:
        Bloco de texto formatado, ou string vazia se o diretório não existir.
    """
    viking_dir = project_repo_path / VIKING_DIR

    if not viking_dir.is_dir():
        return ""

    if domain:
        files = list(viking_dir.glob(f"{domain}.md"))
    else:
        files = sorted(viking_dir.glob("*.md"))

    if not files:
        return ""

    parts: list[str] = []
    total = 0

    for f in files:
        try:
            content = f.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        if not content:
            continue

        header = f"### {f.stem}"
        block = f"{header}\n{content}"

        if total + len(block) > max_chars:
            # Truncar o último bloco se necessário
            remaining = max_chars - total - len(header) - 2
            if remaining > 100:
                parts.append(f"{header}\n{content[:remaining]}…")
            break

        parts.append(block)
        total += len(block)

    return "\n\n".join(parts)


def viking_dir_exists(project_repo_path: Path) -> bool:
    """Verifica se o diretório /docs/viking/ existe no projeto."""
    return (project_repo_path / VIKING_DIR).is_dir()


def list_viking_domains(project_repo_path: Path) -> list[str]:
    """Retorna os nomes dos domínios Viking disponíveis (sem extensão)."""
    viking_dir = project_repo_path / VIKING_DIR
    if not viking_dir.is_dir():
        return []
    return [f.stem for f in sorted(viking_dir.glob("*.md"))]
