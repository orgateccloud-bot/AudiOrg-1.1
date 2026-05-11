"""Middleware de cabeçalhos de segurança HTTP.

Adiciona proteções OWASP recomendadas a todas as respostas:
  - HSTS (Strict-Transport-Security): força HTTPS por 1 ano
  - X-Content-Type-Options: bloqueia MIME-sniffing
  - X-Frame-Options: bloqueia framing (anti-clickjacking)
  - Referrer-Policy: restringe envio de Referer cross-origin
  - Content-Security-Policy: bloqueia inline scripts e fontes externas
  - Permissions-Policy: desliga câmera/mic/geo por padrão
"""
from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Política CSP enxuta para API REST + SPA (Vite/React serve assets estáticos)
_DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
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
        csp: str | None = _DEFAULT_CSP,
        permissions_policy: str = _DEFAULT_PERMISSIONS,
        enable_hsts: bool = True,
    ):
        super().__init__(app)
        self.hsts_max_age = hsts_max_age
        self.csp = csp
        self.permissions_policy = permissions_policy
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        h = response.headers
        # Tipo MIME estrito — bloqueia sniffing
        h.setdefault("X-Content-Type-Options", "nosniff")
        # Anti-clickjacking (defesa em profundidade junto com frame-ancestors)
        h.setdefault("X-Frame-Options", "DENY")
        # Não vaza URL completa em navegação cross-origin
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if self.csp:
            h.setdefault("Content-Security-Policy", self.csp)
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
