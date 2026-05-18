"""Testes do BaseAgent._call_llm() — garante que @Delta é aplicado.

Mocka call_model para inspecionar o prompt final e verificar que
nenhum CPF/CNPJ vaza para o modelo.
"""
from __future__ import annotations

import pytest

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType


class _AgenteFake(BaseAgent):
    agent_id = "A-FAKE"
    name = "@Fake"

    async def process(self, payload: dict) -> AgentResult:
        resp = await self._call_llm(
            model_type=ModelType.HAIKU,
            prompt_payload=payload,
            prompt_template="Dados: {payload}",
            system="sistema técnico",
            max_tokens=100,
        )
        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output={"resp": resp},
            confidence=1.0,
        )


@pytest.mark.asyncio
async def test_call_llm_anonimiza_cpf_antes_de_chamar_modelo(monkeypatch):
    chamadas: list[dict] = []

    async def _fake_call_model(model_type, prompt, system="", max_tokens=4096):
        chamadas.append({
            "model": model_type,
            "prompt": prompt,
            "system": system,
            "max_tokens": max_tokens,
        })
        return '{"ok": true}'

    monkeypatch.setattr(
        "horizon_blue_one.agents.base_agent.call_model",
        _fake_call_model,
    )

    agente = _AgenteFake()
    payload = {
        "contribuinte": {"cpf": "123.456.789-00", "nome": "João Silva"},
        "obs": "CNPJ 12.345.678/0001-99",
    }
    resultado = await agente.process(payload)

    assert resultado.status == "APROVADO"
    assert len(chamadas) == 1
    prompt_enviado = chamadas[0]["prompt"]

    # CPFs/CNPJs NÃO podem aparecer em claro no prompt
    assert "123.456.789-00" not in prompt_enviado
    assert "12.345.678/0001-99" not in prompt_enviado
    assert "João Silva" not in prompt_enviado

    # Placeholders DEVEM aparecer
    assert "[CPF_PROTEGIDO]" in prompt_enviado
    assert "[CNPJ_PROTEGIDO]" in prompt_enviado
    assert "[NOME_REDACTED_" in prompt_enviado


@pytest.mark.asyncio
async def test_call_llm_passa_system_sem_modificar(monkeypatch):
    chamadas: list[dict] = []

    async def _fake_call_model(model_type, prompt, system="", max_tokens=4096):
        chamadas.append({"system": system, "model": model_type})
        return "{}"

    monkeypatch.setattr(
        "horizon_blue_one.agents.base_agent.call_model",
        _fake_call_model,
    )

    agente = _AgenteFake()
    await agente.process({"foo": "bar"})

    # System prompt passa intocado (é texto técnico do agente)
    assert chamadas[0]["system"] == "sistema técnico"
    assert chamadas[0]["model"] == ModelType.HAIKU
