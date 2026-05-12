"""Testes das 4 métricas OrgAudi-específicas (#25)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

# JWT_SECRET_KEY exigido por outros módulos importados em chain
os.environ.setdefault("JWT_SECRET_KEY", "a" * 64)

from api.observability.orgaudi_metrics import (
    ORGAUDI_CLAUDE_COST_USD_TOTAL,
    ORGAUDI_ERRORS_S5_TOTAL,
    ORGAUDI_LAUDOS_TOTAL,
    _espelhar_custo_claude,
    _extrair_componente,
    registrar_erro_s5,
    registrar_laudo,
)
from horizon_blue_one.core.model_adapter import ModelType


def _valor(counter, **labels):
    return counter.labels(**labels)._value.get()


# ── Extrator de componente ───────────────────────────────────────────────────

class TestExtrairComponente:
    def test_raiz(self):
        assert _extrair_componente("/") == "raiz"
        assert _extrair_componente("") == "raiz"

    def test_componente_conhecido(self):
        assert _extrair_componente("/auditoria/nfae") == "auditoria"
        assert _extrair_componente("/auth/login") == "auth"
        assert _extrair_componente("/clientes/42") == "clientes"

    def test_componente_desconhecido(self):
        assert _extrair_componente("/desconhecido/foo") == "outros"
        assert _extrair_componente("/rota-aleatoria") == "outros"


# ── registrar_laudo ──────────────────────────────────────────────────────────

class TestRegistrarLaudo:
    def test_incrementa_status_sucesso(self):
        antes = _valor(ORGAUDI_LAUDOS_TOTAL, status="sucesso")
        registrar_laudo("sucesso")
        assert _valor(ORGAUDI_LAUDOS_TOTAL, status="sucesso") == antes + 1

    def test_incrementa_status_falha(self):
        antes = _valor(ORGAUDI_LAUDOS_TOTAL, status="falha")
        registrar_laudo("falha")
        assert _valor(ORGAUDI_LAUDOS_TOTAL, status="falha") == antes + 1

    def test_status_invalido_vai_para_falha(self):
        antes = _valor(ORGAUDI_LAUDOS_TOTAL, status="falha")
        registrar_laudo("status-bizarro")
        assert _valor(ORGAUDI_LAUDOS_TOTAL, status="falha") == antes + 1


# ── registrar_erro_s5 ────────────────────────────────────────────────────────

class TestRegistrarErroS5:
    def test_incrementa_componente_conhecido(self):
        antes = _valor(ORGAUDI_ERRORS_S5_TOTAL, component="auditoria")
        registrar_erro_s5("/auditoria/nfae")
        assert _valor(ORGAUDI_ERRORS_S5_TOTAL, component="auditoria") == antes + 1

    def test_path_desconhecido_vai_para_outros(self):
        antes = _valor(ORGAUDI_ERRORS_S5_TOTAL, component="outros")
        registrar_erro_s5("/path-aleatorio/foo")
        assert _valor(ORGAUDI_ERRORS_S5_TOTAL, component="outros") == antes + 1


# ── Espelhamento custo Claude ────────────────────────────────────────────────

class TestEspelharCustoClaude:
    def test_haiku_incrementa_counter_orgaudi(self):
        decision = MagicMock()
        antes = _valor(ORGAUDI_CLAUDE_COST_USD_TOTAL, model=ModelType.HAIKU.value)
        # 1M tokens in + 1M out → 0.80 + 4.00 = 4.80 USD
        _espelhar_custo_claude(
            modelo=ModelType.HAIKU,
            tokens_in=1_000_000,
            tokens_out=1_000_000,
            decision=decision,
            max_tokens=None,
            agent_id="a-test",
        )
        depois = _valor(ORGAUDI_CLAUDE_COST_USD_TOTAL, model=ModelType.HAIKU.value)
        assert depois == pytest.approx(antes + 4.80, abs=1e-6)

    def test_zero_tokens_nao_incrementa(self):
        decision = MagicMock()
        antes = _valor(ORGAUDI_CLAUDE_COST_USD_TOTAL, model=ModelType.SONNET.value)
        _espelhar_custo_claude(
            modelo=ModelType.SONNET,
            tokens_in=0,
            tokens_out=0,
            decision=decision,
            max_tokens=None,
            agent_id=None,
        )
        depois = _valor(ORGAUDI_CLAUDE_COST_USD_TOTAL, model=ModelType.SONNET.value)
        assert depois == antes


# ── Integração com PrometheusMiddleware (hook errors_s5) ─────────────────────

class TestMiddlewareIntegracao:
    @pytest.mark.asyncio
    async def test_middleware_chama_registrar_erro_s5_em_5xx(self):
        from api.middleware.prometheus import PrometheusMiddleware

        antes = _valor(ORGAUDI_ERRORS_S5_TOTAL, component="auditoria")

        mw = PrometheusMiddleware(app=None)
        req = MagicMock()
        req.method = "POST"
        req.url.path = "/auditoria/nfae"

        async def _next(_r):
            r = MagicMock()
            r.status_code = 500
            return r

        await mw.dispatch(req, _next)

        depois = _valor(ORGAUDI_ERRORS_S5_TOTAL, component="auditoria")
        assert depois == antes + 1

    @pytest.mark.asyncio
    async def test_middleware_nao_dispara_em_status_2xx(self):
        from api.middleware.prometheus import PrometheusMiddleware

        antes = _valor(ORGAUDI_ERRORS_S5_TOTAL, component="auditoria")

        mw = PrometheusMiddleware(app=None)
        req = MagicMock()
        req.method = "GET"
        req.url.path = "/auditoria/status"

        async def _next(_r):
            r = MagicMock()
            r.status_code = 200
            return r

        await mw.dispatch(req, _next)

        depois = _valor(ORGAUDI_ERRORS_S5_TOTAL, component="auditoria")
        assert depois == antes  # 2xx não incrementa errors_s5


# ── /metrics/prometheus expõe as 4 famílias ──────────────────────────────────

class TestMetricsEndpointFamiliasCompletas:
    def test_endpoint_lista_4_familias_orgaudi(self):
        from fastapi.testclient import TestClient
        from api.main import app

        # Garante que pelo menos um sample existe em cada counter
        registrar_laudo("sucesso")
        registrar_erro_s5("/auditoria/x")
        decision = MagicMock()
        _espelhar_custo_claude(
            modelo=ModelType.SONNET,
            tokens_in=100, tokens_out=100,
            decision=decision, max_tokens=None, agent_id=None,
        )

        client = TestClient(app)
        client.get("/ping")  # gera latency sample
        res = client.get("/metrics/prometheus")
        assert res.status_code == 200
        body = res.text

        # 4 famílias requeridas pela issue #25
        assert "orgaudi_laudos_total"               in body
        assert "http_request_duration_seconds"      in body  # latency (PR #29)
        assert "orgaudi_errors_s5_total"            in body
        assert "orgaudi_claude_cost_usd_total"      in body
