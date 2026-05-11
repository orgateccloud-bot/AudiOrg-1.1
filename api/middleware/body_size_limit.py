"""Middleware de limite de tamanho de requisição.

Rejeita requisições com Content-Length acima de `max_body_size` (bytes) com
413 Payload Too Large. Defende contra exaustão de memória e abuso por upload.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Aplica limite global de Content-Length por requisição."""

    def __init__(self, app, max_body_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_body_size = max_body_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                tamanho = int(cl)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Content-Length inválido"},
                )
            if tamanho > self.max_body_size:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Requisição excede o limite de "
                            f"{self.max_body_size // (1024 * 1024)} MB"
                        )
                    },
                )
        return await call_next(request)
