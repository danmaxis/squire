"""Testes unitários para backends.py — foco na lógica de seleção de agente do OpenCodeBackend."""
from __future__ import annotations

import pytest

from backends import OpenCodeBackend


# ── Helpers ──────────────────────────────────────────────────────────

def hint(
    title: str = "",
    description: str = "",
    attempts: int = 0,
    last_error: str | None = None,
    skip_homologation: bool = False,
) -> dict:
    return {
        "title": title,
        "description": description,
        "attempts": attempts,
        "last_error": last_error,
        "skip_homologation": skip_homologation,
    }


backend = OpenCodeBackend.__new__(OpenCodeBackend)  # instância sem __init__


# ── TestOpenCodeAgentSelection ────────────────────────────────────────

class TestOpenCodeAgentSelection:

    def test_default_retorna_code(self):
        assert backend._select_agent(hint("Implementar listagem de projetos")) == "code"

    def test_vazio_retorna_code(self):
        assert backend._select_agent({}) == "code"

    # ── debug ─────────────────────────────────────────────────────────

    def test_com_last_error_retorna_debug(self):
        assert backend._select_agent(hint(last_error="TypeError: cannot read property")) == "debug"

    def test_stuck_3_tentativas_retorna_debug(self):
        assert backend._select_agent(hint("Adicionar endpoint", attempts=3)) == "debug"

    def test_stuck_5_tentativas_retorna_debug(self):
        assert backend._select_agent(hint("Qualquer coisa", attempts=5)) == "debug"

    def test_titulo_fix_com_erro_retorna_debug(self):
        assert backend._select_agent(hint("Fix login bug", last_error="AssertionError")) == "debug"

    def test_titulo_corrigir_com_erro_retorna_debug(self):
        assert backend._select_agent(hint("Corrigir falha no parser", last_error="SyntaxError")) == "debug"

    def test_titulo_fix_sem_erro_sem_tentativas_nao_retorna_debug(self):
        # Fix no título mas sem erro e poucos attempts → code (não garante debug sem contexto)
        result = backend._select_agent(hint("Fix typo in comment", attempts=0))
        assert result == "code"

    def test_titulo_fix_com_muitas_tentativas_retorna_debug(self):
        assert backend._select_agent(hint("Fix validation", attempts=4)) == "debug"

    # ── terminal ──────────────────────────────────────────────────────

    def test_keyword_migration_retorna_terminal(self):
        assert backend._select_agent(hint("Run database migrations")) == "terminal"

    def test_keyword_seed_retorna_terminal(self):
        assert backend._select_agent(hint("Seed initial data")) == "terminal"

    def test_keyword_script_retorna_terminal(self):
        assert backend._select_agent(hint("Execute setup script")) == "terminal"

    def test_keyword_ambiente_retorna_terminal(self):
        assert backend._select_agent(hint("Verificar ambiente de desenvolvimento")) == "terminal"

    def test_keyword_banco_retorna_terminal(self):
        assert backend._select_agent(hint("", description="Inicializar banco de dados")) == "terminal"

    # ── build ─────────────────────────────────────────────────────────

    def test_keyword_setup_retorna_build(self):
        assert backend._select_agent(hint("Setup inicial do projeto")) == "build"

    def test_keyword_dockerfile_retorna_build(self):
        assert backend._select_agent(hint("Criar Dockerfile para produção")) == "build"

    def test_keyword_scaffold_retorna_build(self):
        assert backend._select_agent(hint("Scaffold estrutura do projeto")) == "build"

    def test_keyword_tsconfig_retorna_build(self):
        assert backend._select_agent(hint("", description="Configurar tsconfig.json")) == "build"

    def test_keyword_boilerplate_retorna_build(self):
        assert backend._select_agent(hint("Criar boilerplate Next.js")) == "build"

    # ── plan ──────────────────────────────────────────────────────────

    def test_skip_homolog_com_design_retorna_plan(self):
        assert backend._select_agent(hint("Design da arquitetura de módulos", skip_homologation=True)) == "plan"

    def test_skip_homolog_com_arquitetura_retorna_plan(self):
        assert backend._select_agent(hint("Definir arquitetura do sistema", skip_homologation=True)) == "plan"

    def test_skip_homolog_sem_keyword_design_nao_retorna_plan(self):
        # skip_homolog mas sem keyword de design → code (não é um plano, é só boilerplate simples)
        result = backend._select_agent(hint("Criar arquivo README", skip_homologation=True))
        assert result != "plan"

    def test_design_sem_skip_homolog_nao_retorna_plan(self):
        # Keyword de design mas sem skip_homologation → code (será homologado normalmente)
        result = backend._select_agent(hint("Design da API"))
        assert result != "plan"

    # ── prioridade de regras ───────────────────────────────────────────

    def test_erro_tem_prioridade_sobre_terminal(self):
        # Tem keyword de terminal mas tem last_error → debug ganha
        result = backend._select_agent(hint("Run migration script", last_error="Connection refused"))
        assert result == "debug"

    def test_erro_tem_prioridade_sobre_build(self):
        result = backend._select_agent(hint("Setup projeto", last_error="npm ERR!"))
        assert result == "debug"

    def test_terminal_tem_prioridade_sobre_build(self):
        # Ambos: seed (terminal) e install (build) → terminal ganha primeiro
        result = backend._select_agent(hint("Seed and install dependencies"))
        assert result == "terminal"
