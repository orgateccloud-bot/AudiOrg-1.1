"""Testes do middleware Prometheus e endpoint /metrics/prometheus."""
import os

os.environ["JWT_SECRET_KEY"] = "a" * 64

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware.prometheus import (
    HTTP_REQUESTS_TOTAL,
    PrometheusMiddleware,
    _normalizar_path,
    render_metrics,
)

client = TestClient(app)


# ── _normalizar_path ─────────────────────────────────────────────────────────

class TestNormalizarPath:
    def test_path_raiz(self):
        assert _normalizar_path("/") == "/"

    def test_substitui_id_numerico(self):
        assert _normalizar_path("/auditoria/status/12345") == "/auditoria/status/:id"

    def test_substitui_uuid_hex(self):
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        assert _normalizar_path(f"/auditoria/resultado/{uuid}") == "/auditoria/resultado/:id"

    def test_mantem_segmentos_textuais(self):
        assert _normalizar_path("/auth/login") == "/auth/login"

    def test_multiplos_ids(self):
        out = _normalizar_path("/api/clientes/42/laudos/777")
        assert out == "/api/clientes/:id/laudos/:id"


# ── Endpoint /metrics/prometheus ─────────────────────────────────────────────

class TestEndpointPrometheus:
    def test_retorna_text_plain_com_metricas(self):
        # Faz pelo menos uma chamada para gerar dados
        client.get("/ping")
        res = client.get("/metrics/prometheus")
        assert res.status_code == 200
        ct = res.headers["content-type"]
        assert "text/plain" in ct
        body = res.text
        # Deve conter métricas-padrão
        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body
        assert "orgaudi_app_info" in body or "orgaudi_app" in body


# ── PrometheusMiddleware ─────────────────────────────────────────────────────

class TestPrometheusMiddleware:
    @pytest.mark.asyncio
    async def test_incrementa_contador_em_request_normal(self):
        mw = PrometheusMiddleware(app=None)
        req = MagicMock()
        req.method = "GET"
        req.url.path = "/qualquer-rota"

        async def _next(_r):
            r = MagicMock()
            r.status_code = 200
            return r

        antes = HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/qualquer-rota", status="200"
        )._value.get()
        await mw.dispatch(req, _next)
        depois = HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/qualquer-rota", status="200"
        )._value.get()
        assert depois == antes + 1

    @pytest.mark.asyncio
    async def test_pula_proprio_endpoint_metrics(self):
        """Endpoint /metrics/prometheus não conta para si mesmo."""
        mw = PrometheusMiddleware(app=None)
        req = MagicMock()
        req.method = "GET"
        req.url.path = "/metrics/prometheus"

        async def _next(_r):
            r = MagicMock()
            r.status_code = 200
            r.headers = {}
            return r

        antes = HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/metrics/prometheus", status="200"
        )._value.get()
        await mw.dispatch(req, _next)
        depois = HTTP_REQUESTS_TOTAL.labels(
            method="GET", path="/metrics/prometheus", status="200"
        )._value.get()
        assert depois == antes  # não incrementou

    @pytest.mark.asyncio
    async def test_excecao_no_handler_registra_status_500(self):
        mw = PrometheusMiddleware(app=None)
        req = MagicMock()
        req.method = "POST"
        req.url.path = "/rota-quebrada"

        async def _next(_r):
            raise RuntimeError("erro proposital")

        antes = HTTP_REQUESTS_TOTAL.labels(
            method="POST", path="/rota-quebrada", status="500"
        )._value.get()
        with pytest.raises(RuntimeError):
            await mw.dispatch(req, _next)
        depois = HTTP_REQUESTS_TOTAL.labels(
            method="POST", path="/rota-quebrada", status="500"
        )._value.get()
        assert depois == antes + 1


# ── render_metrics ───────────────────────────────────────────────────────────

class TestRenderMetrics:
    def test_retorna_response_com_payload(self):
        resp = render_metrics()
        assert resp.status_code == 200
        # body é bytes do Prometheus text format
        assert b"http_requests_total" in resp.body or b"orgaudi_app" in resp.body
