"""Testes do MCP Bridge — schemas, allowlist e dispatcher."""
import json
from unittest.mock import patch

import pytest

from horizon_blue_one.tools.mcp_bridge import (
    _FETCH_ALLOWLIST,
    MCP_TOOLS,
    _buscar_dados_externos,
    _consultar_historico_produtor,
    executar_tool,
)


class TestMcpToolsSchemas:
    def test_dois_tools_definidos(self):
        assert len(MCP_TOOLS) == 2

    def test_tool_historico_tem_required(self):
        tool = next(t for t in MCP_TOOLS if t["name"] == "consultar_historico_produtor")
        assert "documento" in tool["input_schema"]["required"]

    def test_tool_fetch_tem_required(self):
        tool = next(t for t in MCP_TOOLS if t["name"] == "buscar_dados_externos")
        assert "url" in tool["input_schema"]["required"]

    def test_schemas_tem_descricao(self):
        for tool in MCP_TOOLS:
            assert len(tool["description"]) > 20

    def test_input_schema_type_object(self):
        for tool in MCP_TOOLS:
            assert tool["input_schema"]["type"] == "object"


class TestAllowlist:
    def test_sefazgo_autorizado(self):
        assert "sefazgo.gov.br" in _FETCH_ALLOWLIST

    def test_receita_autorizada(self):
        assert "receita.fazenda.gov.br" in _FETCH_ALLOWLIST

    def test_cadin_autorizado(self):
        assert "cadin.fazenda.gov.br" in _FETCH_ALLOWLIST

    def test_dominio_arbitrario_bloqueado(self):
        resultado = _buscar_dados_externos("https://meusite-malicioso.com/api")
        assert resultado["status"] == 403
        assert "não autorizado" in resultado["erro"]

    def test_url_invalida_retorna_erro(self):
        resultado = _buscar_dados_externos("nao_e_uma_url_valida")
        assert "erro" in resultado

    def test_dominio_com_path_bloqueado(self):
        resultado = _buscar_dados_externos("https://evil.com/path?url=sefazgo.gov.br")
        assert resultado["status"] == 403


class TestConsultarHistorico:
    def _db_fake(self):
        from pathlib import Path
        return Path("/tmp/nao_existe_orgaudi_test.db")

    def test_banco_inexistente_retorna_erro(self):
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=self._db_fake()):
            resultado = _consultar_historico_produtor("12345678901")
        assert "erro" in resultado
        assert resultado["notas"] == []

    def test_documento_vazio_nao_quebra(self):
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=self._db_fake()):
            resultado = _consultar_historico_produtor("")
        assert "notas" in resultado

    def test_limite_alto_nao_quebra(self):
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=self._db_fake()):
            resultado = _consultar_historico_produtor("12345678901", limite=9999)
        assert "notas" in resultado


class TestExecutarTool:
    @pytest.mark.asyncio
    async def test_tool_desconhecida_retorna_erro(self):
        resultado_json = await executar_tool("tool_que_nao_existe", {})
        resultado = json.loads(resultado_json)
        assert "erro" in resultado

    @pytest.mark.asyncio
    async def test_buscar_dados_externos_bloqueado(self):
        resultado_json = await executar_tool(
            "buscar_dados_externos",
            {"url": "https://site-nao-autorizado.com/api"}
        )
        resultado = json.loads(resultado_json)
        assert resultado["status"] == 403

    @pytest.mark.asyncio
    async def test_consultar_historico_sem_banco(self):
        from pathlib import Path
        with patch("horizon_blue_one.tools.mcp_bridge._db_path",
                   return_value=Path("/tmp/nao_existe.db")):
            resultado_json = await executar_tool(
                "consultar_historico_produtor",
                {"documento": "12345678901"}
            )
        resultado = json.loads(resultado_json)
        assert "notas" in resultado

    @pytest.mark.asyncio
    async def test_retorno_sempre_json_valido(self):
        resultado_json = await executar_tool("tool_inexistente", {})
        dados = json.loads(resultado_json)
        assert isinstance(dados, dict)
