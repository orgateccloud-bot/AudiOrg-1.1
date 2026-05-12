"""Testes do bootstrap Sentry (#25)."""
from __future__ import annotations

import logging
import os
import sys

import pytest

# JWT_SECRET_KEY exigido por outros módulos importados em chain
os.environ.setdefault("JWT_SECRET_KEY", "a" * 64)


@pytest.fixture(autouse=True)
def _reset_sentry_flag():
    """Reseta o flag idempotente antes de cada teste."""
    from api.observability.sentry_init import reset_sentry_state_for_tests
    reset_sentry_state_for_tests()
    yield
    reset_sentry_state_for_tests()


@pytest.fixture(autouse=True)
def _isolar_env(monkeypatch):
    """Garante que SENTRY_DSN/ENVIRONMENT não vazem entre testes."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
    yield


class TestInitSentry:
    def test_sem_dsn_em_dev_retorna_false_sem_log_warn(self, monkeypatch, caplog):
        from api.observability.sentry_init import init_sentry
        monkeypatch.setenv("ENVIRONMENT", "development")
        with caplog.at_level(logging.WARNING, logger="orgaudi.sentry"):
            assert init_sentry() is False
        assert not any("sem_dsn_em_producao" in r.message for r in caplog.records)

    def test_sem_dsn_em_producao_loga_warning(self, monkeypatch, caplog):
        from api.observability.sentry_init import init_sentry
        monkeypatch.setenv("ENVIRONMENT", "production")
        with caplog.at_level(logging.WARNING, logger="orgaudi.sentry"):
            assert init_sentry() is False
        assert any("sem_dsn_em_producao" in r.message for r in caplog.records)

    def test_com_dsn_inicializa_e_retorna_true(self, monkeypatch):
        from api.observability import sentry_init as si
        chamadas: list[dict] = []

        class _FakeSentry:
            @staticmethod
            def init(**kwargs):
                chamadas.append(kwargs)

        class _FakeFastApi:
            def __init__(self):
                pass

        class _FakeStarlette:
            def __init__(self):
                pass

        monkeypatch.setitem(sys.modules, "sentry_sdk", _FakeSentry)
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk.integrations.fastapi",
            type(sys)("sentry_sdk.integrations.fastapi"),
        )
        sys.modules["sentry_sdk.integrations.fastapi"].FastApiIntegration = _FakeFastApi
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk.integrations.starlette",
            type(sys)("sentry_sdk.integrations.starlette"),
        )
        sys.modules["sentry_sdk.integrations.starlette"].StarletteIntegration = _FakeStarlette

        monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")

        assert si.init_sentry() is True
        assert len(chamadas) == 1
        cfg = chamadas[0]
        assert cfg["dsn"] == "https://fake@sentry.io/1"
        assert cfg["environment"] == "production"
        assert cfg["traces_sample_rate"] == 0.25
        assert cfg["send_default_pii"] is False

    def test_idempotente_chamadas_repetidas_nao_reinit(self, monkeypatch):
        from api.observability import sentry_init as si
        chamadas: list[dict] = []

        class _FakeSentry:
            @staticmethod
            def init(**kwargs):
                chamadas.append(kwargs)

        monkeypatch.setitem(sys.modules, "sentry_sdk", _FakeSentry)
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk.integrations.fastapi",
            type(sys)("sentry_sdk.integrations.fastapi"),
        )
        sys.modules["sentry_sdk.integrations.fastapi"].FastApiIntegration = type(
            "F", (), {"__init__": lambda self: None}
        )
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk.integrations.starlette",
            type(sys)("sentry_sdk.integrations.starlette"),
        )
        sys.modules["sentry_sdk.integrations.starlette"].StarletteIntegration = type(
            "S", (), {"__init__": lambda self: None}
        )

        monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
        assert si.init_sentry() is True
        assert si.init_sentry() is False  # segunda chamada é no-op
        assert len(chamadas) == 1

    def test_traces_sample_rate_invalido_usa_default(self, monkeypatch):
        from api.observability import sentry_init as si

        class _FakeSentry:
            captured: dict = {}

            @staticmethod
            def init(**kwargs):
                _FakeSentry.captured = kwargs

        monkeypatch.setitem(sys.modules, "sentry_sdk", _FakeSentry)
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk.integrations.fastapi",
            type(sys)("sentry_sdk.integrations.fastapi"),
        )
        sys.modules["sentry_sdk.integrations.fastapi"].FastApiIntegration = type(
            "F", (), {"__init__": lambda self: None}
        )
        monkeypatch.setitem(
            sys.modules,
            "sentry_sdk.integrations.starlette",
            type(sys)("sentry_sdk.integrations.starlette"),
        )
        sys.modules["sentry_sdk.integrations.starlette"].StarletteIntegration = type(
            "S", (), {"__init__": lambda self: None}
        )

        monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/1")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "valor_invalido")
        assert si.init_sentry() is True
        assert _FakeSentry.captured["traces_sample_rate"] == 0.1
