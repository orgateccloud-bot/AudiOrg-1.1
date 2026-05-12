"""Testes do middleware de rate limit (backend Redis + fallback in-memory)."""

from __future__ import annotations

import time

import fakeredis
import pytest

from api.middleware.rate_limit import _InMemoryBackend, _RedisBackend, _build_backend


# ── Backend in-memory ────────────────────────────────────────────────────────


class TestInMemoryBackend:
    def test_permite_ate_o_limite(self):
        backend = _InMemoryBackend()
        for _ in range(60):
            permitido, _ = backend.check("ip1", rate=60, window=60)
            assert permitido

    def test_bloqueia_acima_do_limite(self):
        backend = _InMemoryBackend()
        for _ in range(60):
            backend.check("ip1", rate=60, window=60)
        permitido, restante = backend.check("ip1", rate=60, window=60)
        assert not permitido
        assert restante == 0

    def test_ips_diferentes_nao_compartilham_bucket(self):
        backend = _InMemoryBackend()
        for _ in range(60):
            backend.check("ip1", rate=60, window=60)
        permitido, _ = backend.check("ip2", rate=60, window=60)
        assert permitido


# ── Backend Redis (via fakeredis) ────────────────────────────────────────────


@pytest.fixture
def redis_backend(monkeypatch):
    """Cria _RedisBackend usando fakeredis em vez de Redis real."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    backend = _RedisBackend.__new__(_RedisBackend)
    backend._client = fake  # noqa: SLF001
    return backend


class TestRedisBackend:
    def test_permite_ate_o_limite(self, redis_backend):
        for _ in range(60):
            permitido, _ = redis_backend.check("ip1", rate=60, window=60)
            assert permitido

    def test_bloqueia_acima_do_limite(self, redis_backend):
        for _ in range(60):
            redis_backend.check("ip1", rate=60, window=60)
        permitido, restante = redis_backend.check("ip1", rate=60, window=60)
        assert not permitido
        assert restante == 0

    def test_ips_diferentes_nao_compartilham_bucket(self, redis_backend):
        for _ in range(60):
            redis_backend.check("ip1", rate=60, window=60)
        permitido, _ = redis_backend.check("ip2", rate=60, window=60)
        assert permitido

    def test_remaining_decrementa(self, redis_backend):
        _, primeiro = redis_backend.check("ip1", rate=10, window=60)
        _, segundo = redis_backend.check("ip1", rate=10, window=60)
        assert primeiro == 9
        assert segundo == 8

    def test_janela_expira(self, redis_backend, monkeypatch):
        agora = [int(time.time())]
        monkeypatch.setattr(time, "time", lambda: agora[0])
        for _ in range(10):
            redis_backend.check("ip1", rate=10, window=5)
        permitido, _ = redis_backend.check("ip1", rate=10, window=5)
        assert not permitido
        agora[0] += 10
        permitido, _ = redis_backend.check("ip1", rate=10, window=5)
        assert permitido


# ── Factory _build_backend ───────────────────────────────────────────────────


class TestBuildBackend:
    def test_sem_redis_url_em_dev_usa_inmemory(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("ENV", "development")
        backend = _build_backend()
        assert isinstance(backend, _InMemoryBackend)

    def test_sem_redis_url_em_prod_levanta(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("ENV", "production")
        with pytest.raises(RuntimeError, match="REDIS_URL é obrigatório"):
            _build_backend()

    def test_redis_url_inacessivel_em_dev_cai_para_inmemory(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # porta inválida
        monkeypatch.setenv("ENV", "development")
        backend = _build_backend()
        assert isinstance(backend, _InMemoryBackend)

    def test_redis_url_inacessivel_em_prod_levanta(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
        monkeypatch.setenv("ENV", "production")
        with pytest.raises(RuntimeError, match="inacessível"):
            _build_backend()
