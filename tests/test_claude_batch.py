"""Testes do helper Anthropic Message Batches."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from horizon_blue_one.core.claude_batch import (
    BatchRequest,
    BatchResult,
    _decodificar,
    _resolve_model_id,
    batch_results,
    batch_status,
    estimar_economia_usd,
    submit_batch,
)
from horizon_blue_one.core.model_adapter import ModelType

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_client():
    """Cliente Anthropic falso com .messages.batches.*"""
    return MagicMock()


def _resp_succeeded(text="ok", t_in=10, t_out=5):
    """Constrói um item de resultado do tipo succeeded."""
    usage = SimpleNamespace(input_tokens=t_in, output_tokens=t_out)
    block = SimpleNamespace(type="text", text=text)
    msg   = SimpleNamespace(content=[block], usage=usage)
    result = SimpleNamespace(type="succeeded", message=msg)
    return SimpleNamespace(custom_id="cid", result=result)


def _resp_errored(msg="boom"):
    inner = SimpleNamespace(message=msg)
    err   = SimpleNamespace(error=inner)
    result = SimpleNamespace(type="errored", error=err)
    return SimpleNamespace(custom_id="cid-err", result=result)


# ── BatchRequest.to_payload ───────────────────────────────────────────────────

class TestBatchRequest:
    def test_payload_haiku_sem_system(self):
        req = BatchRequest(custom_id="a", model=ModelType.HAIKU, prompt="hi")
        p = req.to_payload()
        assert p["custom_id"] == "a"
        assert p["params"]["max_tokens"] == 1024
        assert p["params"]["messages"] == [{"role": "user", "content": "hi"}]
        assert "system" not in p["params"]

    def test_payload_com_system_inclui_system(self):
        req = BatchRequest(custom_id="b", model=ModelType.SONNET,
                           prompt="q", system="you are X", max_tokens=256)
        p = req.to_payload()
        assert p["params"]["system"] == "you are X"
        assert p["params"]["max_tokens"] == 256


class TestResolveModelId:
    def test_haiku(self):
        assert "haiku" in _resolve_model_id(ModelType.HAIKU).lower()

    def test_sonnet_e_claude_resolvem_iguais(self):
        assert _resolve_model_id(ModelType.SONNET) == _resolve_model_id(ModelType.CLAUDE)

    def test_opus(self):
        assert "opus" in _resolve_model_id(ModelType.OPUS).lower()

    def test_invalido_levanta(self):
        with pytest.raises(ValueError):
            _resolve_model_id("xyz")  # type: ignore[arg-type]


# ── submit_batch ──────────────────────────────────────────────────────────────

class TestSubmitBatch:
    def test_envia_payloads_e_retorna_id(self, fake_client):
        fake_client.messages.batches.create.return_value = SimpleNamespace(id="batch_123")
        reqs = [
            BatchRequest("a", ModelType.HAIKU, "p1"),
            BatchRequest("b", ModelType.SONNET, "p2", system="s"),
        ]
        bid = submit_batch(reqs, client=fake_client)
        assert bid == "batch_123"

        called = fake_client.messages.batches.create.call_args.kwargs
        assert len(called["requests"]) == 2
        assert called["requests"][0]["custom_id"] == "a"
        assert called["requests"][1]["params"]["system"] == "s"

    def test_lista_vazia_levanta(self, fake_client):
        with pytest.raises(ValueError):
            submit_batch([], client=fake_client)
        fake_client.messages.batches.create.assert_not_called()


# ── batch_status ──────────────────────────────────────────────────────────────

class TestBatchStatus:
    def test_retorna_processing_status(self, fake_client):
        fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
            processing_status="in_progress"
        )
        assert batch_status("bid", client=fake_client) == "in_progress"

    def test_ended(self, fake_client):
        fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
            processing_status="ended"
        )
        assert batch_status("bid", client=fake_client) == "ended"


# ── batch_results / _decodificar ──────────────────────────────────────────────

class TestBatchResults:
    def test_yield_succeeded(self, fake_client):
        fake_client.messages.batches.results.return_value = iter([
            _resp_succeeded(text="resposta-1", t_in=100, t_out=20),
        ])
        out = list(batch_results("bid", client=fake_client))
        assert len(out) == 1
        r = out[0]
        assert r.status == "succeeded"
        assert r.text == "resposta-1"
        assert r.input_tokens == 100
        assert r.output_tokens == 20

    def test_yield_mistura_succeeded_e_errored(self, fake_client):
        fake_client.messages.batches.results.return_value = iter([
            _resp_succeeded(text="ok"),
            _resp_errored(msg="rate limited"),
        ])
        out = list(batch_results("bid", client=fake_client))
        assert [r.status for r in out] == ["succeeded", "errored"]
        assert out[1].error == "rate limited"
        assert out[1].text == ""


class TestDecodificar:
    def test_succeeded_concatena_text_blocks(self):
        msg = SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="ola "),
                SimpleNamespace(type="text", text="mundo"),
            ],
            usage=SimpleNamespace(input_tokens=5, output_tokens=2),
        )
        raw = SimpleNamespace(
            custom_id="x",
            result=SimpleNamespace(type="succeeded", message=msg),
        )
        r = _decodificar(raw)
        assert r.text == "ola mundo"
        assert r.input_tokens == 5

    def test_succeeded_sem_text_block_retorna_string_vazia(self):
        msg = SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input={})],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
        raw = SimpleNamespace(
            custom_id="y",
            result=SimpleNamespace(type="succeeded", message=msg),
        )
        assert _decodificar(raw).text == ""

    def test_sem_result_devolve_errored(self):
        raw = SimpleNamespace(custom_id="z", result=None)
        r = _decodificar(raw)
        assert r.status == "errored"
        assert r.text == ""

    def test_expired(self):
        raw = SimpleNamespace(
            custom_id="w",
            result=SimpleNamespace(type="expired"),
        )
        assert _decodificar(raw).status == "expired"

    def test_canceled(self):
        raw = SimpleNamespace(
            custom_id="c",
            result=SimpleNamespace(type="canceled"),
        )
        assert _decodificar(raw).status == "canceled"


# ── Economia estimada ─────────────────────────────────────────────────────────

class TestEstimarEconomia:
    def test_haiku_economia_positiva(self):
        # 1000 chars prompt + 0 system ≈ 250 input tokens; max 256 output
        reqs = [BatchRequest("a", ModelType.HAIKU, "x" * 1000, max_tokens=256)]
        e = estimar_economia_usd(reqs)
        # Custo sync: (250 * 0.8 + 256 * 4.0)/1e6 = 0.001224 → batch poupa metade
        assert e == pytest.approx(0.000612, rel=1e-3)

    def test_lote_vazio_zero(self):
        assert estimar_economia_usd([]) == 0.0

    def test_opus_economiza_mais_que_haiku(self):
        haiku = estimar_economia_usd([BatchRequest("a", ModelType.HAIKU, "x" * 1000, max_tokens=256)])
        opus  = estimar_economia_usd([BatchRequest("a", ModelType.OPUS, "x" * 1000, max_tokens=256)])
        assert opus > haiku


# ── BatchResult dataclass smoke ───────────────────────────────────────────────

def test_batch_result_defaults():
    r = BatchResult(custom_id="x", text="", status="errored")
    assert r.error is None
    assert r.input_tokens == 0
