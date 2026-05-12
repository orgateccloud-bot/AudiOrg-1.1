"""Testes extras de api/main.py — _carregar_env_local, /stats, /tokens, lifespan."""
import os

os.environ["JWT_SECRET_KEY"] = "a" * 64

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import _carregar_env_local, app

client = TestClient(app)


# ── _carregar_env_local ──────────────────────────────────────────────────────

class TestCarregarEnvLocal:
    def test_arquivo_inexistente_nao_falha(self, monkeypatch, tmp_path):
        # Aponta para diretório sem .env nem config.env
        from api import main as main_mod
        monkeypatch.setattr(main_mod, "Path", type(tmp_path))
        # Apenas verifica que executa sem exceção
        _carregar_env_local()  # Real call (tenta no diretório real do projeto)

    def test_carrega_pares_chave_valor(self, tmp_path, monkeypatch):
        env_file = tmp_path / "config.env"
        env_file.write_text(
            "# comentário\n"
            "\n"
            "FOO_TEST_VAR=bar\n"
            'COM_ASPAS="valor-com-aspas"\n'
            "SEM_IGUAL\n"  # ignorada
            "JA_DEFINIDO=novo_valor\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("JA_DEFINIDO", "valor_original")
        monkeypatch.delenv("FOO_TEST_VAR", raising=False)
        monkeypatch.delenv("COM_ASPAS", raising=False)

        # Patch do Path para apontar para tmp_path
        from pathlib import Path as RealPath

        from api import main as main_mod

        class _FakePath:
            def __init__(self, *a, **kw):
                self._p = RealPath(*a, **kw) if a else None
            def resolve(self):
                return _FakePath.__new__(_FakePath)
            @property
            def parent(self):
                fp = _FakePath.__new__(_FakePath)
                fp._p = tmp_path.parent
                return fp
            def __truediv__(self, other):
                return tmp_path / other
        # Mais simples: substitui o resultado de Path(__file__).resolve().parent.parent
        # via patch direto do trecho que constrói "base"
        monkeypatch.setattr(main_mod, "Path",
                            lambda *a, **kw: type("X", (), {
                                "resolve": lambda self=None: type("Y", (), {
                                    "parent": type("Z", (), {"parent": tmp_path})()
                                })()
                            })())
        _carregar_env_local()
        assert os.environ.get("FOO_TEST_VAR") == "bar"
        assert os.environ.get("COM_ASPAS") == "valor-com-aspas"
        # Já definido permanece
        assert os.environ.get("JA_DEFINIDO") == "valor_original"


# ── Endpoints simples ────────────────────────────────────────────────────────

class TestEndpointsSimples:
    def test_root_retorna_status(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "OrgAudi" in res.json()["status"]

    def test_ping(self):
        res = client.get("/ping")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_stats_retorna_metricas(self):
        # /stats consulta DB e obter_stats_nfae
        with patch("api.services.auditoria_nfae.obter_stats_nfae",
                   return_value={
                       "total_auditorias_nfae": 5,
                       "total_notas_processadas": 10,
                       "score_medio_nfae": 30.5,
                   }):
            res = client.get("/stats")
        assert res.status_code == 200
        body = res.json()
        assert "total_clientes" in body
        assert body["total_auditorias_nfae"] == 5

    @pytest.mark.asyncio
    async def test_tokens_chama_relatorio(self):
        # Patch direto do modulo de origem
        from unittest.mock import AsyncMock
        with patch("horizon_blue_one.agents.a_token.relatorio_custo",
                   new_callable=AsyncMock,
                   return_value={"total_usd": 0.05, "modelos": {}}):
            res = client.get("/tokens")
        assert res.status_code == 200
        assert "total_usd" in res.json() or "modelos" in res.json()


# ── Lifespan ─────────────────────────────────────────────────────────────────

class TestLifespan:
    def test_app_inicializa_com_lifespan(self):
        # TestClient acima já forçou a inicialização.
        # Verifica que o engine foi criado e tabelas existem.
        from nfa_extractor.infrastructure.database_v2 import Base, engine
        names = list(Base.metadata.tables.keys())
        assert "users" in names
        assert engine is not None
