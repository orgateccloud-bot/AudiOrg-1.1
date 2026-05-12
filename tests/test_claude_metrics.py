"""Testes das métricas Prometheus de uso e custo do Claude."""
from __future__ import annotations

import pytest

from api.middleware.claude_metrics import (
    CLAUDE_CALLS_TOTAL,
    CLAUDE_COST_USD_TOTAL,
    CLAUDE_ECONOMIA_VS_SONNET,
    CLAUDE_OUTPUT_SATURATION,
    CLAUDE_ROUTING_TOTAL,
    CLAUDE_TOKENS_TOTAL,
    _publicar,
)
from horizon_blue_one.core.model_adapter import ModelType
from horizon_blue_one.core.token_router import (
    TipoTarefa,
    registrar_uso,
    reset_stats,
    rotear,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_stats()
    yield
    reset_stats()


def _valor_counter(counter, **labels):
    """Lê o valor atual de um Counter com labels (Prometheus client API)."""
    return counter.labels(**labels)._value.get()


def _valor_counter_sem_label(counter):
    return counter._value.get()


def _soma_histogram_count(hist, **labels):
    return hist.labels(**labels)._sum.get()


class TestPublicar:
    def test_haiku_incrementa_calls_e_tokens(self):
        antes_calls = _valor_counter(CLAUDE_CALLS_TOTAL, modelo="haiku")
        antes_in = _valor_counter(CLAUDE_TOKENS_TOTAL, modelo="haiku", direcao="input")

        d = rotear(TipoTarefa.LGPD)
        _publicar(ModelType.HAIKU, 1000, 500, d, max_tokens=512, agent_id="S1")

        assert _valor_counter(CLAUDE_CALLS_TOTAL, modelo="haiku") == antes_calls + 1
        assert _valor_counter(CLAUDE_TOKENS_TOTAL, modelo="haiku", direcao="input") == antes_in + 1000
        assert _valor_counter(CLAUDE_TOKENS_TOTAL, modelo="haiku", direcao="output") >= 500

    def test_custo_haiku_calculado_corretamente(self):
        antes = _valor_counter(CLAUDE_COST_USD_TOTAL, modelo="haiku")
        d = rotear(TipoTarefa.LGPD)
        # 1M input + 1M output em Haiku = 0.80 + 4.00 = $4.80
        _publicar(ModelType.HAIKU, 1_000_000, 1_000_000, d, max_tokens=None, agent_id=None)
        delta = _valor_counter(CLAUDE_COST_USD_TOTAL, modelo="haiku") - antes
        assert delta == pytest.approx(4.80, rel=1e-6)

    def test_economia_vs_sonnet_haiku(self):
        antes = _valor_counter_sem_label(CLAUDE_ECONOMIA_VS_SONNET)
        d = rotear(TipoTarefa.LGPD)
        # Em Sonnet seriam $3 + $15 = $18; em Haiku $4.80 → economia $13.20
        _publicar(ModelType.HAIKU, 1_000_000, 1_000_000, d, max_tokens=None, agent_id=None)
        delta = _valor_counter_sem_label(CLAUDE_ECONOMIA_VS_SONNET) - antes
        assert delta == pytest.approx(13.20, rel=1e-6)

    def test_upgrade_para_opus_conta_em_routing(self):
        antes = _valor_counter(CLAUDE_ROUTING_TOTAL, decisao="upgrade_opus")
        d = rotear(TipoTarefa.FORENSE, score_risco=90)
        assert d.upgrade_aplicado
        _publicar(ModelType.OPUS, 100, 50, d, max_tokens=1024, agent_id="A-07")
        assert _valor_counter(CLAUDE_ROUTING_TOTAL, decisao="upgrade_opus") == antes + 1

    def test_downgrade_para_haiku_conta(self):
        antes = _valor_counter(CLAUDE_ROUTING_TOTAL, decisao="downgrade_haiku")
        d = rotear(TipoTarefa.AUDITORIA, score_risco=10)
        assert d.downgrade_aplicado
        _publicar(d.modelo, 100, 50, d, max_tokens=512, agent_id="S5")
        assert _valor_counter(CLAUDE_ROUTING_TOTAL, decisao="downgrade_haiku") == antes + 1

    def test_decisao_base_quando_sem_escalada(self):
        antes = _valor_counter(CLAUDE_ROUTING_TOTAL, decisao="base")
        d = rotear(TipoTarefa.LGPD)  # Haiku base, sem upgrade/downgrade
        _publicar(ModelType.HAIKU, 100, 50, d, max_tokens=512, agent_id="S1")
        assert _valor_counter(CLAUDE_ROUTING_TOTAL, decisao="base") == antes + 1

    def test_saturation_registrada_quando_max_tokens_informado(self):
        antes = _soma_histogram_count(CLAUDE_OUTPUT_SATURATION, modelo="haiku")
        d = rotear(TipoTarefa.LGPD)
        # output 256 / max 512 = 0.5
        _publicar(ModelType.HAIKU, 100, 256, d, max_tokens=512, agent_id="S1")
        depois = _soma_histogram_count(CLAUDE_OUTPUT_SATURATION, modelo="haiku")
        assert depois - antes == pytest.approx(0.5, rel=1e-6)

    def test_saturation_clamp_em_1_quando_output_excede(self):
        antes = _soma_histogram_count(CLAUDE_OUTPUT_SATURATION, modelo="haiku")
        d = rotear(TipoTarefa.LGPD)
        # output 1000 > max 512 → clamp para 1.0
        _publicar(ModelType.HAIKU, 100, 1000, d, max_tokens=512, agent_id="S1")
        depois = _soma_histogram_count(CLAUDE_OUTPUT_SATURATION, modelo="haiku")
        assert depois - antes == pytest.approx(1.0, rel=1e-6)

    def test_saturation_nao_registra_quando_max_tokens_zero_ou_none(self):
        antes = _soma_histogram_count(CLAUDE_OUTPUT_SATURATION, modelo="haiku")
        d = rotear(TipoTarefa.LGPD)
        _publicar(ModelType.HAIKU, 100, 100, d, max_tokens=None, agent_id=None)
        _publicar(ModelType.HAIKU, 100, 100, d, max_tokens=0, agent_id=None)
        depois = _soma_histogram_count(CLAUDE_OUTPUT_SATURATION, modelo="haiku")
        assert depois == antes


class TestIntegracaoComRegistrarUso:
    """Garante que registrar_uso propaga corretamente ao listener Prometheus."""

    def test_registrar_uso_chama_publicar(self):
        # claude_metrics auto-subscreve no import — o módulo já foi importado
        # pelos imports do topo. registrar_uso deve disparar _publicar.
        antes = _valor_counter(CLAUDE_CALLS_TOTAL, modelo="haiku")
        d = rotear(TipoTarefa.LGPD)
        registrar_uso(ModelType.HAIKU, 1, 1, d, max_tokens=256, agent_id="S1")
        assert _valor_counter(CLAUDE_CALLS_TOTAL, modelo="haiku") == antes + 1

    def test_registrar_uso_sem_max_tokens_nao_quebra(self):
        # Compatibilidade retroativa: chamadas antigas sem max_tokens funcionam.
        d = rotear(TipoTarefa.LGPD)
        registrar_uso(ModelType.HAIKU, 1, 1, d)  # sem max_tokens
