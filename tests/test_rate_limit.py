"""Testes do RateLimitMiddleware — _TokenBucket isolado e middleware.

NOTA: o conftest global tem autouse que monkeypatcha _TokenBucket.is_allowed.
Aqui usamos `restaurar_token_bucket` para reverter a cada teste e exercitar a lógica real.
"""
import time
from unittest.mock import MagicMock

import pytest

from api.middleware.rate_limit import RateLimitMiddleware, _TokenBucket

# Salva a implementação original ANTES do conftest patchar
_IS_ALLOWED_ORIGINAL = _TokenBucket.__dict__.get("is_allowed")


@pytest.fixture(autouse=True)
def restaurar_token_bucket(monkeypatch):
    """Restaura o is_allowed original (conftest faz bypass global)."""
    if _IS_ALLOWED_ORIGINAL is not None:
        monkeypatch.setattr(_TokenBucket, "is_allowed", _IS_ALLOWED_ORIGINAL)


# ── _TokenBucket ─────────────────────────────────────────────────────────────

class TestTokenBucket:
    def test_permite_dentro_da_taxa(self):
        b = _TokenBucket(rate=3, window=60)
        for i in range(3):
            allowed, restantes = b.is_allowed("ip1")
            assert allowed is True
            assert restantes == 2 - i

    def test_bloqueia_quando_excede(self):
        b = _TokenBucket(rate=2, window=60)
        b.is_allowed("ip1"); b.is_allowed("ip1")
        allowed, restantes = b.is_allowed("ip1")
        assert allowed is False
        assert restantes == 0

    def test_buckets_separados_por_chave(self):
        b = _TokenBucket(rate=1, window=60)
        a1, _ = b.is_allowed("ip-a")
        a2, _ = b.is_allowed("ip-a")
        b1, _ = b.is_allowed("ip-b")
        assert a1 is True
        assert a2 is False
        assert b1 is True

    def test_remove_timestamps_fora_da_janela(self, monkeypatch):
        """Janela 1s: após avanço de tempo, slots antigos são removidos."""
        b = _TokenBucket(rate=2, window=1.0)
        # Primeira chamada
        t0 = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: t0)
        b.is_allowed("ip"); b.is_allowed("ip")
        allowed_full, _ = b.is_allowed("ip")
        assert allowed_full is False
        # Avança 2s — janela expira
        monkeypatch.setattr(time, "monotonic", lambda: t0 + 2.0)
        allowed_pos, restantes = b.is_allowed("ip")
        assert allowed_pos is True
        assert restantes == 1


# ── RateLimitMiddleware (sem bypass do conftest) ─────────────────────────────

class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_ping_sempre_passa_sem_consumir(self):
        """/ping NUNCA deve consumir tokens (skip)."""
        mw = RateLimitMiddleware(app=None, rate=1, window=60)
        req = MagicMock()
        req.url.path = "/ping"
        req.client = MagicMock(host="1.2.3.4")

        async def _next(_r):
            r = MagicMock()
            r.headers = {}
            return r

        # 5 chamadas em /ping: nenhuma 429
        for _ in range(5):
            res = await mw.dispatch(req, _next)
            assert res.status_code != 429 if hasattr(res, "status_code") else True

    @pytest.mark.asyncio
    async def test_excedeu_limite_retorna_429(self):
        mw = RateLimitMiddleware(app=None, rate=1, window=60)
        req = MagicMock()
        req.url.path = "/qualquer"
        req.client = MagicMock(host="9.9.9.9")

        async def _next(_r):
            r = MagicMock()
            r.headers = {}
            return r

        # Primeira passa
        await mw.dispatch(req, _next)
        # Segunda → 429
        res2 = await mw.dispatch(req, _next)
        assert res2.status_code == 429
        assert "Retry-After" in res2.headers

    @pytest.mark.asyncio
    async def test_client_none_usa_unknown(self):
        mw = RateLimitMiddleware(app=None, rate=10, window=60)
        req = MagicMock()
        req.url.path = "/x"
        req.client = None

        async def _next(_r):
            r = MagicMock()
            r.headers = {}
            return r

        res = await mw.dispatch(req, _next)
        # Não levanta — usa "unknown"
        assert "X-RateLimit-Remaining" in res.headers
