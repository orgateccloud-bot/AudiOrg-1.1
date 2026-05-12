"""Testes do BaseAgent (parse_json_response, retry, confidence) e do ledger."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core import ledger as ledger_mod
from horizon_blue_one.core.ledger import async_log_event, log_event_sync


# ── AgentResult ──────────────────────────────────────────────────────────────

class TestAgentResult:
    def test_gera_timestamp_e_hash(self):
        r = AgentResult(
            agent_id="X", status="APROVADO",
            output={"a": 1}, confidence=0.9,
        )
        assert r.timestamp != ""
        assert len(r.audit_hash) > 0

    def test_audit_hash_estavel_para_mesmo_output(self):
        r1 = AgentResult(agent_id="X", status="OK", output={"a": 1}, confidence=1.0)
        r2 = AgentResult(agent_id="X", status="OK", output={"a": 1}, confidence=1.0)
        assert r1.audit_hash == r2.audit_hash

    def test_audit_hash_muda_quando_output_muda(self):
        r1 = AgentResult(agent_id="X", status="OK", output={"a": 1}, confidence=1.0)
        r2 = AgentResult(agent_id="X", status="OK", output={"a": 2}, confidence=1.0)
        assert r1.audit_hash != r2.audit_hash


# ── BaseAgent.parse_json_response ────────────────────────────────────────────

class TestParseJsonResponse:
    def test_json_valido_completo(self):
        data, ok = BaseAgent.parse_json_response(
            '{"score": 80, "nivel": "ALTO"}',
            fallback={"score": 0},
            campos_esperados=("score", "nivel"),
        )
        assert ok is True
        assert data["score"] == 80

    def test_json_valido_faltando_campos_aplica_fallback_e_marca_falso(self):
        data, ok = BaseAgent.parse_json_response(
            '{"score": 80}',
            fallback={"score": 0, "nivel": "DESCONHECIDO"},
            campos_esperados=("score", "nivel"),
        )
        assert ok is False
        assert data["nivel"] == "DESCONHECIDO"
        assert data["score"] == 80

    def test_nao_dict_retorna_fallback(self):
        data, ok = BaseAgent.parse_json_response(
            '[1, 2, 3]',
            fallback={"x": 1},
        )
        assert ok is False
        assert data == {"x": 1}

    def test_json_malformado_retorna_fallback(self):
        data, ok = BaseAgent.parse_json_response(
            "isso não é json",
            fallback={"safe": True},
        )
        assert ok is False
        assert data["safe"] is True


# ── BaseAgent.derivar_confidence ─────────────────────────────────────────────

class TestDerivarConfidence:
    def test_nao_dict_retorna_0_50(self):
        assert BaseAgent.derivar_confidence(True, None) == 0.50  # type: ignore[arg-type]

    def test_parseou_ok_com_todos_campos_usa_base(self):
        c = BaseAgent.derivar_confidence(
            True, {"a": 1, "b": 2},
            campos_esperados=("a", "b"),
        )
        assert c == 0.85

    def test_parseou_ok_com_metade_campos_reduz(self):
        c = BaseAgent.derivar_confidence(
            True, {"a": 1, "b": None},  # b é falsy → não conta
            campos_esperados=("a", "b"),
        )
        assert c < 0.85

    def test_parseou_falso_corta_pela_metade(self):
        c = BaseAgent.derivar_confidence(
            False, {"a": 1},
            campos_esperados=("a",),
        )
        assert c == 0.50

    def test_confianca_declarada_no_dict_sobrescreve(self):
        c = BaseAgent.derivar_confidence(
            True, {"a": 1, "confianca": 0.42},
            campos_esperados=("a",),
        )
        assert c == 0.42

    def test_confianca_declarada_fora_range_e_ignorada(self):
        c = BaseAgent.derivar_confidence(
            True, {"a": 1, "confianca": 1.5},
            campos_esperados=("a",),
        )
        assert c == 0.85


# ── BaseAgent.call_com_retry (com call_otimizado mockado) ────────────────────

class TestCallComRetry:
    @pytest.mark.asyncio
    async def test_primeiro_acerto_retorna_imediatamente(self):
        async def mock_call_otim(prompt, system, **kw):
            return '{"a": 1, "b": 2}', None

        with patch(
            "horizon_blue_one.agents.a_token.call_otimizado",
            side_effect=mock_call_otim,
        ):
            data, ok, resp = await BaseAgent.call_com_retry(
                "prompt", "system", ("a", "b"), "A-X",
            )
        assert ok is True
        assert data == {"a": 1, "b": 2}

    @pytest.mark.asyncio
    async def test_retry_apos_json_invalido(self):
        chamadas = []

        async def mock_call_otim(prompt, system, **kw):
            chamadas.append(prompt)
            if len(chamadas) == 1:
                return "lixo", None
            return '{"a": 1}', None

        with patch(
            "horizon_blue_one.agents.a_token.call_otimizado",
            side_effect=mock_call_otim,
        ):
            data, ok, resp = await BaseAgent.call_com_retry(
                "p", "s", ("a",), "A-X",
            )
        assert ok is True
        assert data["a"] == 1
        assert len(chamadas) == 2

    @pytest.mark.asyncio
    async def test_retorna_fallback_se_falhar_todas_tentativas(self):
        async def mock_call_otim(prompt, system, **kw):
            return "ainda inválido", None

        with patch(
            "horizon_blue_one.agents.a_token.call_otimizado",
            side_effect=mock_call_otim,
        ):
            data, ok, resp = await BaseAgent.call_com_retry(
                "p", "s", ("a",), "A-X", max_tentativas=2,
            )
        assert ok is False
        assert data == {}


# ── ledger ───────────────────────────────────────────────────────────────────

class TestLedger:
    @pytest.mark.asyncio
    async def test_async_log_event_grava_jsonl(self, tmp_path, monkeypatch):
        path = tmp_path / "ledger.jsonl"
        monkeypatch.setattr(ledger_mod, "_LEDGER_PATH", path)
        await async_log_event(
            requisicao_id="r-1",
            agent_id="A-99",
            acao="teste",
            payload={"x": 1},
        )
        linhas = path.read_text(encoding="utf-8").strip().split("\n")
        evento = json.loads(linhas[0])
        assert evento["agent_id"] == "A-99"
        assert evento["payload"]["x"] == 1
        assert evento["status"] == "APROVADO"

    @pytest.mark.asyncio
    async def test_async_log_event_sem_payload_default_dict_vazio(self, tmp_path, monkeypatch):
        path = tmp_path / "ledger.jsonl"
        monkeypatch.setattr(ledger_mod, "_LEDGER_PATH", path)
        await async_log_event(requisicao_id="r", agent_id="A", acao="x")
        evento = json.loads(path.read_text().strip())
        assert evento["payload"] == {}

    @pytest.mark.asyncio
    async def test_erro_io_nao_propaga(self, monkeypatch):
        # Path inválido → garante que exceção é capturada
        monkeypatch.setattr(ledger_mod, "_LEDGER_PATH", Path("Z:/path/que/nao/existe/x.jsonl"))
        # Não deve levantar
        await async_log_event(requisicao_id="r", agent_id="A", acao="x")

    def test_log_event_sync_funciona(self, tmp_path, monkeypatch):
        path = tmp_path / "ledger.jsonl"
        monkeypatch.setattr(ledger_mod, "_LEDGER_PATH", path)
        log_event_sync(requisicao_id="r-2", agent_id="A-X", acao="sync")
        assert path.exists()
