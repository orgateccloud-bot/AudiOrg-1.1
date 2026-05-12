"""Middleware de cabeçalhos de segurança HTTP.

Adiciona proteções OWASP recomendadas a todas as respostas:
  - HSTS (Strict-Transport-Security): força HTTPS por 1 ano
  - X-Content-Type-Options: bloqueia MIME-sniffing
  - X-Frame-Options: bloqueia framing (anti-clickjacking)
  - Referrer-Policy: restringe envio de Referer cross-origin
  - Content-Security-Policy: bloqueia inline scripts; nonce por request
  - Permissions-Policy: desliga câmera/mic/geo por padrão

O CSP é gerado por request com nonce aleatório (16 bytes base64). O nonce
é exposto em `request.state.csp_nonce` para templates injetarem em <script>
e <style> tags inline (ex: nonce="{{ request.state.csp_nonce }}").
"""
from __future__ import annotations

import base64
import secrets
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


def _gerar_nonce() -> str:
    """Nonce base64 url-safe de 16 bytes (128 bits de entropia)."""
    return base64.b64encode(secrets.token_bytes(16)).decode("ascii")


def _csp_com_nonce(nonce: str) -> str:
    """Monta CSP com nonce dinâmico — elimina 'unsafe-inline' em style/script."""
    return (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        f"style-src 'self' 'nonce-{nonce}'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

_DEFAULT_PERMISSIONS = (
    "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Aplica cabeçalhos de segurança em todas as respostas."""

    def __init__(
        self,
        app,
        hsts_max_age: int = 31_536_000,    # 1 ano
        csp: str | None = None,            # None → CSP dinâmico com nonce
        permissions_policy: str = _DEFAULT_PERMISSIONS,
        enable_hsts: bool = True,
    ):
        super().__init__(app)
        self.hsts_max_age = hsts_max_age
        # Se csp explícito for passado, usa-o estático; senão gera por request
        self.csp_estatico = csp
        self.permissions_policy = permissions_policy
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Gera nonce e expõe via request.state para uso em templates
        nonce = _gerar_nonce()
        request.state.csp_nonce = nonce

        response = await call_next(request)
        h = response.headers
        # Tipo MIME estrito — bloqueia sniffing
        h.setdefault("X-Content-Type-Options", "nosniff")
        # Anti-clickjacking (defesa em profundidade junto com frame-ancestors)
        h.setdefault("X-Frame-Options", "DENY")
        # Não vaza URL completa em navegação cross-origin
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        csp_final = self.csp_estatico if self.csp_estatico else _csp_com_nonce(nonce)
        h.setdefault("Content-Security-Policy", csp_final)
        h.setdefault("Permissions-Policy", self.permissions_policy)
        # HSTS — só ativa em produção (sob HTTPS); inseguro em http localhost
        if self.enable_hsts and request.url.scheme == "https":
            h.setdefault(
                "Strict-Transport-Security",
                f"max-age={self.hsts_max_age}; includeSubDomains",
            )
        # Remove headers que vazam stack (Server, X-Powered-By)
        for leak in ("Server", "X-Powered-By"):
            if leak in h:
                del h[leak]
        return response
