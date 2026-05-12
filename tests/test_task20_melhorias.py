"""Testes para Task #20:
- MCP allowlist via YAML
- bug token budget paralelo (ondas baratos/caros)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── MCP allowlist YAML ──────────────────────────────────────────────────────

class TestMcpAllowlistYaml:
    def test_carrega_dominios_do_yaml(self, tmp_path, monkeypatch):
        """YAML versionado é a fonte canônica quando presente."""
        from horizon_blue_one.tools import mcp_bridge as mb
        yaml_file = tmp_path / "mcp_allowlist.yaml"
        yaml_file.write_text(
            "dominios:\n"
            "  - exemplo.gov.br\n"
            "  - api.teste.com\n",
            encoding="utf-8",
        )

        # Aponta _ler_yaml_allowlist para nosso arquivo
        from pathlib import Path
        original = Path.__truediv__
        # Mais simples: faz patch do Path retornado
        import horizon_blue_one.tools.mcp_bridge as mb_mod

        def _ler_fake() -> frozenset[str]:
            return frozenset({"exemplo.gov.br", "api.teste.com"})

        monkeypatch.setattr(mb_mod, "_ler_yaml_allowlist", _ler_fake)
        monkeypatch.delenv("MCP_FETCH_ALLOWLIST", raising=False)
        out = mb._carregar_allowlist()
        assert "exemplo.gov.br" in out
        assert "api.teste.com" in out

    def test_env_override_combina_com_yaml(self, monkeypatch):
        """env adiciona ao YAML (não substitui)."""
        from horizon_blue_one.tools import mcp_bridge as mb
        monkeypatch.setenv("MCP_FETCH_ALLOWLIST", "extra1.com,extra2.com")
        out = mb._carregar_allowlist()
        # YAML real do projeto + extras
        assert "extra1.com" in out
        assert "extra2.com" in out
        assert "sefazgo.gov.br" in out  # do YAML

    def test_yaml_ausente_usa_fallback_hardcoded(self, monkeypatch):
        from horizon_blue_one.tools import mcp_bridge as mb
        # Faz YAML retornar vazio
        monkeypatch.setattr(mb, "_ler_yaml_allowlist", lambda: frozenset())
        monkeypatch.delenv("MCP_FETCH_ALLOWLIST", raising=False)
        out = mb._carregar_allowlist()
        assert "sefazgo.gov.br" in out
        assert "nfe.fazenda.gov.br" in out

    def test_yaml_invalido_nao_falha(self, tmp_path, monkeypatch):
        """YAML mal-formado → warning + fallback."""
        from horizon_blue_one.tools import mcp_bridge as mb
        from pathlib import Path
        yaml_file = tmp_path / "mcp_allowlist.yaml"
        yaml_file.write_text("isto: nao: eh: yaml: valido:", encoding="utf-8")
        # Patch da Path para apontar para tmp
        monkeypatch.setattr(
            "horizon_blue_one.tools.mcp_bridge.Path",
            lambda *a, **kw: type("P", (), {
                "parent": tmp_path,
                "exists": lambda self=None: True,
                "read_text": lambda self=None, encoding="utf-8": yaml_file.read_text(encoding=encoding),
            })()
        )
        # Não deve levantar
        out = mb._ler_yaml_allowlist()
        assert isinstance(out, frozenset)

    def test_yaml_real_do_projeto_carrega(self):
        from horizon_blue_one.tools.mcp_bridge import _ler_yaml_allowlist
        out = _ler_yaml_allowlist()
        # YAML do projeto contém pelo menos esses
        assert "sefazgo.gov.br" in out
        assert "cidades.ibge.gov.br" in out


# ── Bug token budget paralelo ───────────────────────────────────────────────

class TestBudgetParalelo:
    @pytest.mark.asyncio
    async def test_executa_em_ondas_baratos_e_caros(self):
        """Onda 1 = S1/S3/S5/S6, Onda 2 = S2/S4."""
        from horizon_blue_one.agents.base_agent import AgentResult
        from horizon_blue_one.core import orchestrator as orch_mod
        from horizon_blue_one.core.orchestrator import Orchestrator

        ordem = []

        async def _exec_um(self, aid, payload):
            ordem.append(aid)
            return aid, AgentResult(agent_id=aid, status="APROVADO",
                                    output={}, confidence=0.9)

        with patch.object(Orchestrator, "_executar_um", _exec_um):
            o = Orchestrator()
            o.bus = MagicMock()
            o.bus.publish = AsyncMock()
            resultados = await o._executar_paralelo(
                ["S2", "S1", "S5", "S4"],
                {"__orcamento_tokens__": 0, "__tokens_inicio__": 0},
            )
        # Onda 1 (S1, S5) deve estar ANTES de Onda 2 (S2, S4)
        idx_baratos = max(ordem.index("S1"), ordem.index("S5"))
        idx_caros = min(ordem.index("S2"), ordem.index("S4"))
        assert idx_baratos < idx_caros
        assert len(resultados) == 4

    @pytest.mark.asyncio
    async def test_pula_onda_cara_quando_budget_excedido(self):
        """Se snapshot_stats reportar tokens > orçamento entre ondas, pula caros."""
        from horizon_blue_one.agents.base_agent import AgentResult
        from horizon_blue_one.core.orchestrator import Orchestrator

        executados = []

        async def _exec_um(self, aid, payload):
            executados.append(aid)
            return aid, AgentResult(agent_id=aid, status="APROVADO",
                                    output={}, confidence=0.9)

        # Simula consumo alto após Onda 1
        with patch.object(Orchestrator, "_executar_um", _exec_um), \
             patch("horizon_blue_one.core.token_router.snapshot_stats",
                   return_value={"total_tokens": 99_999}):
            o = Orchestrator()
            o.bus = MagicMock()
            o.bus.publish = AsyncMock()
            resultados = await o._executar_paralelo(
                ["S2", "S1", "S4"],
                {"__orcamento_tokens__": 1000, "__tokens_inicio__": 0},
            )
        # S1 (barato) executou; S2 e S4 (caros) foram pulados
        assert "S1" in executados
        assert "S2" not in executados
        assert "S4" not in executados
        assert "S1" in resultados

    @pytest.mark.asyncio
    async def test_so_caros_executa_sem_onda_barata(self):
        """Pipeline com apenas S2 (caro) ainda funciona."""
        from horizon_blue_one.agents.base_agent import AgentResult
        from horizon_blue_one.core.orchestrator import Orchestrator

        async def _exec_um(self, aid, payload):
            return aid, AgentResult(agent_id=aid, status="APROVADO",
                                    output={}, confidence=0.9)

        with patch.object(Orchestrator, "_executar_um", _exec_um):
            o = Orchestrator()
            o.bus = MagicMock()
            o.bus.publish = AsyncMock()
            resultados = await o._executar_paralelo(
                ["S2"], {"__orcamento_tokens__": 0, "__tokens_inicio__": 0},
            )
        assert "S2" in resultados


# ── S6 skip-LLM ───────────────────────────────────────────────────────────

class TestS6SkipLLM:
    @pytest.mark.asyncio
    async def test_microprodutor_sem_pendencia_pula_llm(self):
        from horizon_blue_one.agents.s6_rh import RHAgent
        # call_otimizado NÃO deve ser chamado
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new_callable=AsyncMock) as spy:
            r = await RHAgent().process({
                "esocial_data": {"trabalhadores": 2},
                "contribuinte": {},
            })
        spy.assert_not_called()
        assert r.output["fonte"] == "deterministico"
        assert r.confidence == 0.82

    @pytest.mark.asyncio
    async def test_trabalhadores_acima_do_limite_chama_llm(self):
        from horizon_blue_one.agents.s6_rh import RHAgent
        import json
        resp = json.dumps({
            "eventos_pendentes": [], "divergencias_inss": 0.0,
            "fgts_a_recolher": 0.0, "alertas": [], "conformidade": "CONFORME",
        })
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})) as spy:
            r = await RHAgent().process({
                "esocial_data": {"trabalhadores": 100},
                "contribuinte": {},
            })
        spy.assert_called_once()
        # output não tem "fonte" deterministico
        assert r.output.get("fonte") != "deterministico"

    @pytest.mark.asyncio
    async def test_inss_divergencia_quebra_trivial(self):
        from horizon_blue_one.agents.s6_rh import RHAgent
        import json
        resp = json.dumps({
            "eventos_pendentes": [], "divergencias_inss": 500.0,
            "fgts_a_recolher": 0.0, "alertas": [], "conformidade": "DIVERGENTE",
        })
        with patch("horizon_blue_one.agents.s6_rh.call_otimizado",
                   new_callable=AsyncMock, return_value=(resp, {})) as spy:
            await RHAgent().process({
                "esocial_data": {"trabalhadores": 2, "inss_divergencia": 500},
                "contribuinte": {},
            })
        # inss_divergencia > 0 → não é trivial → LLM
        spy.assert_called_once()
