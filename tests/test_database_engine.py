"""Testes para a seleção de engine em database_v2 (#23).

Política coberta:
- DATABASE_URL postgres -> tenta Postgres; em dev cai para SQLite se falhar
- DATABASE_URL postgres em produção sem cluster -> RuntimeError
- DATABASE_URL ausente em produção -> RuntimeError
- DATABASE_URL ausente em dev -> SQLite WAL fallback
- DATABASE_URL sqlite custom -> respeitada
- Migration 001 aplica limpa em SQLite e cria todas as tabelas (incluindo audit_tasks)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect


# ── Engine selection ─────────────────────────────────────────────────────────


class TestEngineSelection:

    @pytest.fixture
    def reload_module(self, monkeypatch):
        """Recarrega database_v2 para que get_engine() leia o env atual."""
        def _reload():
            import importlib
            from nfa_extractor.infrastructure import database_v2
            importlib.reload(database_v2)
            return database_v2
        return _reload

    def test_sem_database_url_em_dev_usa_sqlite(self, monkeypatch, reload_module):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("ENV", "development")
        mod = reload_module()
        assert mod.engine.url.drivername.startswith("sqlite")

    def test_sem_database_url_em_producao_falha(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("ENV", "production")
        from nfa_extractor.infrastructure.database_v2 import get_engine
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            get_engine()

    def test_postgres_indisponivel_em_dev_cai_para_sqlite(self, monkeypatch, reload_module):
        # Postgres em porta inexistente — falha de conexão deve cair para SQLite em dev
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://user:pwd@127.0.0.1:1/inexistente",
        )
        monkeypatch.setenv("ENV", "development")
        mod = reload_module()
        assert mod.engine.url.drivername.startswith("sqlite")

    def test_postgres_indisponivel_em_producao_falha(self, monkeypatch):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://user:pwd@127.0.0.1:1/inexistente",
        )
        monkeypatch.setenv("ENV", "production")
        from nfa_extractor.infrastructure.database_v2 import get_engine
        with pytest.raises(RuntimeError, match="Postgres"):
            get_engine()

    def test_sqlite_custom_url_respeitada(self, monkeypatch, reload_module, tmp_path):
        custom_db = tmp_path / "custom.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{custom_db}")
        monkeypatch.setenv("ENV", "development")
        mod = reload_module()
        assert str(custom_db).replace("\\", "/") in mod.engine.url.render_as_string(hide_password=False).replace("\\", "/")


# ── Migration 001 cross-DB ───────────────────────────────────────────────────


class TestMigracao001:

    def test_apply_em_sqlite_cria_todas_tabelas(self, tmp_path, monkeypatch):
        """Aplica 001_initial em SQLite e confirma que todas as tabelas surgem."""
        from alembic import command
        from alembic.config import Config

        db_file = tmp_path / "schema_test.db"
        db_url = f"sqlite:///{db_file}"

        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("ENV", "development")

        alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")

        from sqlalchemy import create_engine
        eng = create_engine(db_url)
        insp = inspect(eng)
        tabelas = set(insp.get_table_names())
        # alembic_version é criada pelo próprio alembic
        esperadas = {"users", "clientes", "notas", "produtos", "laudos", "audit_tasks"}
        assert esperadas.issubset(tabelas), f"faltando: {esperadas - tabelas}"

    def test_audit_tasks_tem_colunas_obrigatorias(self, tmp_path, monkeypatch):
        """audit_tasks (não existia no schema original) precisa ter as colunas do model."""
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine

        db_file = tmp_path / "audit_test.db"
        db_url = f"sqlite:///{db_file}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("ENV", "development")

        cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")

        eng = create_engine(db_url)
        cols = {c["name"] for c in inspect(eng).get_columns("audit_tasks")}
        esperadas = {"task_id", "status", "progress", "payload_json", "created_at", "updated_at"}
        assert esperadas.issubset(cols), f"faltando: {esperadas - cols}"

    def test_downgrade_remove_todas_tabelas(self, tmp_path, monkeypatch):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine

        db_file = tmp_path / "downgrade_test.db"
        db_url = f"sqlite:///{db_file}"
        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("ENV", "development")

        cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        eng = create_engine(db_url)
        tabelas = set(inspect(eng).get_table_names())
        sem_negocio = tabelas - {"alembic_version"}
        assert sem_negocio == set(), f"sobraram tabelas após downgrade: {sem_negocio}"
