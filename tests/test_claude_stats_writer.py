"""Testes do writer batched de stats Claude → Postgres (#27)."""
from __future__ import annotations

import os

# JWT_SECRET_KEY exigido por outros módulos importados em chain
os.environ.setdefault("JWT_SECRET_KEY", "a" * 64)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from horizon_blue_one.core import claude_stats_writer as csw
from nfa_extractor.infrastructure.database_v2 import Base, ClaudeStats


@pytest.fixture
def session_factory_isolada():
    """Engine SQLite in-memory por teste, com todas as tabelas criadas."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    SessionLocalLocal = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    yield SessionLocalLocal
    eng.dispose()


@pytest.fixture(autouse=True)
def _reset_buffer():
    csw.reset_buffer_para_testes()
    yield
    csw.reset_buffer_para_testes()


# ── Cálculo de custo ─────────────────────────────────────────────────────────

class TestCalculoCusto:
    def test_haiku_1m_in_1m_out(self):
        # Haiku: 0.80 in + 4.00 out por 1M tokens = 4.80 USD
        custo = csw._calcular_custo("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert custo == pytest.approx(4.80, abs=1e-6)

    def test_sonnet_500k_in_100k_out(self):
        # Sonnet: 3.00 * 0.5 + 15.00 * 0.1 = 1.5 + 1.5 = 3.0 USD
        custo = csw._calcular_custo("claude-sonnet-4-6", 500_000, 100_000)
        assert custo == pytest.approx(3.00, abs=1e-6)

    def test_modelo_desconhecido_retorna_zero(self):
        assert csw._calcular_custo("modelo-fictio", 1_000_000, 1_000_000) == 0.0


# ── Periodo atual ────────────────────────────────────────────────────────────

class TestPeriodoAtual:
    def test_formato_hora_truncada_utc(self):
        p = csw._periodo_atual()
        # YYYY-MM-DDTHH:00:00Z
        assert p.endswith(":00:00Z")
        assert "T" in p


# ── registrar_call (sem flush imediato) ──────────────────────────────────────

class TestRegistrarCall:
    def test_acumula_no_buffer_in_memory(self):
        csw.registrar_call("claude-sonnet-4-6", 1000, 500, flush_auto=False)
        chave = (csw._periodo_atual(), "claude-sonnet-4-6")
        assert csw._BUFFER[chave]["calls"]      == 1
        assert csw._BUFFER[chave]["tokens_in"]  == 1000
        assert csw._BUFFER[chave]["tokens_out"] == 500
        assert csw._BUFFER[chave]["cost_usd"]   > 0

    def test_calls_mesmo_modelo_somam(self):
        csw.registrar_call("claude-sonnet-4-6", 100, 50, flush_auto=False)
        csw.registrar_call("claude-sonnet-4-6", 200, 100, flush_auto=False)
        csw.registrar_call("claude-sonnet-4-6", 50, 25, flush_auto=False)
        chave = (csw._periodo_atual(), "claude-sonnet-4-6")
        assert csw._BUFFER[chave]["calls"]      == 3
        assert csw._BUFFER[chave]["tokens_in"]  == 350
        assert csw._BUFFER[chave]["tokens_out"] == 175

    def test_modelos_diferentes_geram_chaves_separadas(self):
        csw.registrar_call("claude-haiku-4-5", 100, 50, flush_auto=False)
        csw.registrar_call("claude-sonnet-4-6", 100, 50, flush_auto=False)
        assert len(csw._BUFFER) == 2

    def test_custo_explicito_substitui_calculado(self):
        csw.registrar_call(
            "claude-sonnet-4-6", 1000, 500,
            custo_usd=99.99, flush_auto=False,
        )
        chave = (csw._periodo_atual(), "claude-sonnet-4-6")
        assert csw._BUFFER[chave]["cost_usd"] == pytest.approx(99.99)


# ── flush() ──────────────────────────────────────────────────────────────────

class TestFlush:
    def test_flush_de_buffer_vazio_retorna_zero(self, session_factory_isolada):
        assert csw.flush(session_factory=session_factory_isolada) == 0

    def test_flush_insere_linha_nova(self, session_factory_isolada):
        csw.registrar_call("claude-sonnet-4-6", 1000, 500, flush_auto=False)
        n = csw.flush(session_factory=session_factory_isolada)
        assert n == 1
        with session_factory_isolada() as db:
            linhas = db.query(ClaudeStats).all()
            assert len(linhas) == 1
            assert linhas[0].modelo == "claude-sonnet-4-6"
            assert linhas[0].calls == 1
            assert linhas[0].tokens_in == 1000
            assert linhas[0].tokens_out == 500

    def test_flush_acumula_em_linha_existente(self, session_factory_isolada):
        # Primeiro flush cria a linha
        csw.registrar_call("claude-sonnet-4-6", 1000, 500, flush_auto=False)
        csw.flush(session_factory=session_factory_isolada)
        # Segundo flush deve somar na mesma linha (mesmo periodo+modelo)
        csw.registrar_call("claude-sonnet-4-6", 200, 100, flush_auto=False)
        csw.flush(session_factory=session_factory_isolada)
        with session_factory_isolada() as db:
            linhas = db.query(ClaudeStats).all()
            assert len(linhas) == 1  # UMA linha agregada
            assert linhas[0].calls      == 2
            assert linhas[0].tokens_in  == 1200
            assert linhas[0].tokens_out == 600

    def test_1000_calls_em_um_modelo_produzem_uma_linha(self, session_factory_isolada):
        """Critério explícito da issue #27."""
        for _ in range(1_000):
            csw.registrar_call(
                "claude-sonnet-4-6", 100, 50, flush_auto=False,
            )
        csw.flush(session_factory=session_factory_isolada)
        with session_factory_isolada() as db:
            linhas = db.query(ClaudeStats).filter_by(
                modelo="claude-sonnet-4-6",
            ).all()
            assert len(linhas) == 1
            assert linhas[0].calls      == 1_000
            assert linhas[0].tokens_in  == 100_000
            assert linhas[0].tokens_out == 50_000
            # Custo: 1M tokens in * 3.00 + 500k out * 15.00 = 3.0 + 7.5 = 10.5
            # Mas 100k in * 3.00/1M = 0.3 e 50k out * 15.00/1M = 0.75 → 1.05
            assert linhas[0].cost_usd_acumulado == pytest.approx(1.05, abs=1e-3)

    def test_1000_calls_com_3_modelos_produzem_3_linhas(self, session_factory_isolada):
        modelos = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]
        for i in range(1_000):
            csw.registrar_call(
                modelos[i % 3], 100, 50, flush_auto=False,
            )
        csw.flush(session_factory=session_factory_isolada)
        with session_factory_isolada() as db:
            linhas = db.query(ClaudeStats).all()
            assert len(linhas) == 3
            soma_calls = sum(linha.calls for linha in linhas)
            assert soma_calls == 1_000

    def test_flush_auto_dispara_em_100_calls(self, session_factory_isolada, monkeypatch):
        # Faz o SessionLocal apontar para a engine isolada
        monkeypatch.setattr(csw, "SessionLocal", session_factory_isolada)
        for _ in range(100):
            csw.registrar_call("claude-sonnet-4-6", 10, 5)  # flush_auto=True default
        # Após exatamente 100 chamadas, deve ter feito flush
        with session_factory_isolada() as db:
            linhas = db.query(ClaudeStats).all()
            assert len(linhas) == 1
            assert linhas[0].calls == 100
        # Buffer foi limpo pelo flush automático
        assert csw._TOTAL_CALLS_DESDE_FLUSH == 0
