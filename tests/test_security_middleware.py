"""Testes dos middlewares de segurança (headers, body size, CORS estrito)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.body_size_limit import BodySizeLimitMiddleware
from api.middleware.security_headers import SecurityHeadersMiddleware

# ── SecurityHeadersMiddleware ────────────────────────────────────────────────

def _app_com_security_headers(enable_hsts: bool = False) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=enable_hsts)

    @app.get("/test")
    def get_test():
        return {"ok": True}

    return app


class TestSecurityHeaders:
    def test_x_content_type_options_nosniff(self):
        client = TestClient(_app_com_security_headers())
        resp = client.get("/test")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options_deny(self):
        client = TestClient(_app_com_security_headers())
        resp = client.get("/test")
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_referrer_policy_definido(self):
        client = TestClient(_app_com_security_headers())
        resp = client.get("/test")
        assert "strict-origin-when-cross-origin" in resp.headers["Referrer-Policy"]

    def test_csp_definido_por_padrao(self):
        client = TestClient(_app_com_security_headers())
        resp = client.get("/test")
        csp = resp.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_permissions_policy_bloqueia_recursos(self):
        client = TestClient(_app_com_security_headers())
        resp = client.get("/test")
        pp = resp.headers["Permissions-Policy"]
        assert "camera=()" in pp
        assert "microphone=()" in pp
        assert "geolocation=()" in pp

    def test_hsts_ausente_quando_http(self):
        # TestClient usa http://testserver — HSTS não deve ser aplicado
        client = TestClient(_app_com_security_headers(enable_hsts=True))
        resp = client.get("/test")
        assert "Strict-Transport-Security" not in resp.headers

    def test_hsts_ausente_quando_disabled(self):
        client = TestClient(_app_com_security_headers(enable_hsts=False))
        resp = client.get("/test")
        assert "Strict-Transport-Security" not in resp.headers


# ── BodySizeLimitMiddleware ──────────────────────────────────────────────────

def _app_com_body_limit(max_bytes: int = 100) -> FastAPI:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_body_size=max_bytes)

    @app.post("/upload")
    def upload(data: dict):
        return {"len": len(str(data))}

    return app


class TestBodySizeLimit:
    def test_requisicao_pequena_passa(self):
        client = TestClient(_app_com_body_limit(max_bytes=1000))
        resp = client.post("/upload", json={"x": 1})
        assert resp.status_code == 200

    def test_requisicao_grande_rejeitada_413(self):
        client = TestClient(_app_com_body_limit(max_bytes=10))
        resp = client.post(
            "/upload",
            json={"x": "carga muito grande para passar pelo limite"},
        )
        assert resp.status_code == 413
        assert "limite" in resp.json()["detail"].lower()

    def test_content_length_invalido_400(self):
        client = TestClient(_app_com_body_limit())
        resp = client.post(
            "/upload",
            content=b"{}",
            headers={"Content-Length": "abc", "Content-Type": "application/json"},
        )
        # Starlette pode reescrever — aceitamos 400 ou 422 dependendo do caminho
        assert resp.status_code in (400, 422)

    def test_get_sem_content_length_passa(self):
        app = FastAPI()
        app.add_middleware(BodySizeLimitMiddleware, max_body_size=10)

        @app.get("/x")
        def get_x():
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/x").status_code == 200
