"""Testes do model_adapter — cliente Claude com retry, caching, tool_use (MCP)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from horizon_blue_one.core.model_adapter import (
    ModelType,
    _build_system_param,
    call_model,
    call_model_with_tools,
)


# ── _build_system_param ──────────────────────────────────────────────────────

class TestBuildSystemParam:
    def test_string_nao_vazia_gera_lista_com_cache_control(self):
        out = _build_system_param("Você é o @Forense")
        assert isinstance(out, list)
        assert out[0]["type"] == "text"
        assert out[0]["text"] == "Você é o @Forense"
        assert out[0]["cache_control"] == {"type": "ephemeral"}

    def test_string_vazia_retorna_none(self):
        assert _build_system_param("") is None
        assert _build_system_param(None) is None


# ── ModelType ────────────────────────────────────────────────────────────────

class TestModelType:
    def test_valores_canonicos(self):
        assert ModelType.SONNET.value == "sonnet"
        assert ModelType.HAIKU.value == "haiku"
        assert ModelType.OPUS.value == "opus"
        assert ModelType.CLAUDE.value == "claude"


# ── call_model (com Claude mockado) ──────────────────────────────────────────

class TestCallModel:
    @pytest.mark.asyncio
    async def test_call_model_retorna_texto(self):
        resp_mock = MagicMock()
        resp_mock.content = [MagicMock(text="resposta")]

        client_mock = MagicMock()
        client_mock.messages.create = AsyncMock(return_value=resp_mock)

        with patch(
            "horizon_blue_one.core.model_adapter._get_claude",
            return_value=client_mock,
        ):
            out = await call_model(ModelType.HAIKU, "oi")
        assert out == "resposta"

    @pytest.mark.asyncio
    async def test_call_model_envia_system_quando_fornecido(self):
        resp_mock = MagicMock()
        resp_mock.content = [MagicMock(text="ok")]
        client_mock = MagicMock()
        client_mock.messages.create = AsyncMock(return_value=resp_mock)

        with patch(
            "horizon_blue_one.core.model_adapter._get_claude",
            return_value=client_mock,
        ):
            await call_model(ModelType.SONNET, "x", system="Voce eh foo")

        kwargs = client_mock.messages.create.call_args.kwargs
        assert "system" in kwargs
        assert kwargs["system"][0]["text"] == "Voce eh foo"

    @pytest.mark.asyncio
    async def test_call_model_omite_system_quando_vazio(self):
        resp_mock = MagicMock()
        resp_mock.content = [MagicMock(text="ok")]
        client_mock = MagicMock()
        client_mock.messages.create = AsyncMock(return_value=resp_mock)

        with patch(
            "horizon_blue_one.core.model_adapter._get_claude",
            return_value=client_mock,
        ):
            await call_model(ModelType.HAIKU, "x")

        kwargs = client_mock.messages.create.call_args.kwargs
        assert "system" not in kwargs

    @pytest.mark.asyncio
    async def test_modelo_invalido_levanta(self):
        with pytest.raises(ValueError, match="não suportado"):
            await call_model("modelo-fake", "x")  # type: ignore[arg-type]


# ── call_model_with_tools (tool_use loop) ────────────────────────────────────

class TestCallModelWithTools:
    @pytest.mark.asyncio
    async def test_sem_tools_delega_para_call_model(self):
        resp_mock = MagicMock()
        resp_mock.content = [MagicMock(text="resposta direta")]
        client_mock = MagicMock()
        client_mock.messages.create = AsyncMock(return_value=resp_mock)

        with patch(
            "horizon_blue_one.core.model_adapter._get_claude",
            return_value=client_mock,
        ):
            texto, uso = await call_model_with_tools(ModelType.HAIKU, "x")

        assert texto == "resposta direta"
        assert uso == {"input_tokens": 0, "output_tokens": 0, "tool_calls": 0}

    @pytest.mark.asyncio
    async def test_loop_executa_tool_e_retoma(self):
        # Round 1: stop_reason=tool_use → executa ferramenta
        # Round 2: stop_reason=end_turn → retorna texto
        # Nota: kwarg name= no MagicMock define o nome de debug, não o atributo
        tool_use_block = MagicMock(type="tool_use", id="t1", input={"x": 1})
        tool_use_block.name = "ping"
        round1 = MagicMock()
        round1.content = [tool_use_block]
        round1.stop_reason = "tool_use"
        round1.usage = MagicMock(input_tokens=10, output_tokens=5)

        text_block = MagicMock(type="text", text="final")
        round2 = MagicMock()
        round2.content = [text_block]
        round2.stop_reason = "end_turn"
        round2.usage = MagicMock(input_tokens=8, output_tokens=4)

        client_mock = MagicMock()
        client_mock.messages.create = AsyncMock(side_effect=[round1, round2])

        handler = AsyncMock(return_value="resultado-da-tool")

        with patch(
            "horizon_blue_one.core.model_adapter._get_claude",
            return_value=client_mock,
        ):
            texto, uso = await call_model_with_tools(
                ModelType.SONNET,
                prompt="audit",
                tools=[{"name": "ping", "description": "p", "input_schema": {}}],
                tool_handler=handler,
            )

        assert texto == "final"
        assert uso["tool_calls"] == 1
        assert uso["input_tokens"] == 18
        assert uso["output_tokens"] == 9
        handler.assert_awaited_once_with("ping", {"x": 1})

    @pytest.mark.asyncio
    async def test_modelo_invalido_levanta_com_tools(self):
        with pytest.raises(ValueError, match="não suportado"):
            await call_model_with_tools(
                "fake",  # type: ignore[arg-type]
                "x",
                tools=[{"name": "t"}],
                tool_handler=AsyncMock(),
            )
