"""Testes do token_router — roteamento, escalada, downgrade e estatísticas."""
import pytest

from horizon_blue_one.core.model_adapter import ModelType
from horizon_blue_one.core.token_router import (
    TipoTarefa,
    estimar_tokens,
    get_stats,
    max_tokens_para,
    registrar_uso,
    reset_stats,
    rotear,
    snapshot_stats,
)


@pytest.fixture(autouse=True)
def _zera_stats():
    reset_stats()
    yield
    reset_stats()


# ── max_tokens_para ──────────────────────────────────────────────────────────

class TestMaxTokensPara:
    def test_agente_conhecido(self):
        assert max_tokens_para("A-01") == 10
        assert max_tokens_para("S2") == 2048
        assert max_tokens_para("A-08") == 1024

    def test_agente_desconhecido_usa_fallback(self):
        assert max_tokens_para("X-99") == 1024
        assert max_tokens_para("X-99", fallback=512) == 512

    def test_none_usa_fallback(self):
        assert max_tokens_para(None) == 1024


# ── rotear() ─────────────────────────────────────────────────────────────────

class TestRotear:
    def test_haiku_para_tarefa_operacional(self):
        d = rotear(TipoTarefa.LGPD)
        assert d.modelo == ModelType.HAIKU
        assert not d.upgrade_aplicado
        assert not d.downgrade_aplicado

    def test_sonnet_para_forense(self):
        d = rotear(TipoTarefa.FORENSE)
        assert d.modelo == ModelType.SONNET

    def test_opus_para_forense_critico(self):
        d = rotear(TipoTarefa.FORENSE_CRITICO)
        assert d.modelo == ModelType.OPUS

    def test_escala_para_opus_quando_score_85(self):
        d = rotear(TipoTarefa.FORENSE, score_risco=90)
        assert d.modelo == ModelType.OPUS
        assert d.upgrade_aplicado
        assert "85" in d.motivo

    def test_escala_para_opus_quando_3_tipologias_criticas(self):
        d = rotear(TipoTarefa.AUDITORIA, score_risco=10,
                   tipologias_criticas=3)
        assert d.modelo == ModelType.OPUS
        assert d.upgrade_aplicado

    def test_escala_para_opus_quando_prob_autuacao_alta(self):
        d = rotear(TipoTarefa.FORENSE, score_risco=10,
                   probabilidade_autuacao=0.80)
        assert d.modelo == ModelType.OPUS
        assert "75" in d.motivo

    def test_downgrade_auditoria_operacional_score_baixo(self):
        # AUDITORIA com score<50 e sem tipologias → Haiku
        d = rotear(TipoTarefa.AUDITORIA, score_risco=30)
        assert d.modelo == ModelType.HAIKU
        assert d.downgrade_aplicado

    def test_downgrade_classico_score_muito_baixo_e_poucas_notas(self):
        # JURIDICO com score<25 e ≤5 notas (não-forense, não-DECISAO) → Haiku
        d = rotear(TipoTarefa.JURIDICO, score_risco=10, num_notas=3)
        assert d.modelo == ModelType.HAIKU
        assert d.downgrade_aplicado

    def test_sem_downgrade_se_for_forense(self):
        d = rotear(TipoTarefa.FORENSE, score_risco=10, num_notas=2)
        assert d.modelo == ModelType.SONNET
        assert not d.downgrade_aplicado

    def test_agent_id_sobrescreve_tipo_tarefa(self):
        # A-01 mapeia para ROTEAMENTO (Haiku)
        d = rotear(TipoTarefa.FORENSE_CRITICO, agent_id="A-01")
        assert d.modelo == ModelType.HAIKU

    def test_s2_forense_escala_para_opus_em_score_alto(self):
        d = rotear(TipoTarefa.AUDITORIA, agent_id="S2", score_risco=90)
        assert d.modelo == ModelType.OPUS


# ── Estatísticas ─────────────────────────────────────────────────────────────

class TestStats:
    def test_registrar_uso_atualiza_chamadas(self):
        d = rotear(TipoTarefa.LGPD)
        registrar_uso(ModelType.HAIKU, 100, 50, d)
        stats = get_stats()
        assert stats["chamadas_por_modelo"]["haiku"] == 1
        assert stats["tokens_totais"]["input"] == 100
        assert stats["tokens_totais"]["output"] == 50

    def test_distribuicao_em_pct(self):
        d = rotear(TipoTarefa.LGPD)
        for _ in range(3):
            registrar_uso(ModelType.HAIKU, 10, 5, d)
        stats = get_stats()
        assert "100.0%" in stats["distribuicao"]["haiku"]

    def test_economia_vs_sonnet_positiva_para_haiku(self):
        # Haiku é mais barato que Sonnet → economia > 0
        d = rotear(TipoTarefa.LGPD)
        registrar_uso(ModelType.HAIKU, 1_000_000, 1_000_000, d)
        stats = get_stats()
        assert stats["economia_vs_sonnet_usd"] > 0

    def test_upgrades_e_downgrades_contam(self):
        d_up = rotear(TipoTarefa.FORENSE, score_risco=90)
        d_dn = rotear(TipoTarefa.AUDITORIA, score_risco=10)
        registrar_uso(d_up.modelo, 1, 1, d_up)
        registrar_uso(d_dn.modelo, 1, 1, d_dn)
        stats = get_stats()
        assert stats["upgrades_para_opus"] == 1
        assert stats["downgrades_para_haiku"] == 1


class TestSnapshotEReset:
    def test_snapshot_devolve_dicionarios(self):
        d = rotear(TipoTarefa.LGPD)
        registrar_uso(ModelType.HAIKU, 100, 50, d)
        snap = snapshot_stats()
        assert snap["chamadas"]["haiku"] == 1
        assert "resumo" in snap

    def test_reset_zera_tudo(self):
        d = rotear(TipoTarefa.LGPD)
        registrar_uso(ModelType.HAIKU, 100, 50, d)
        reset_stats()
        stats = get_stats()
        assert stats["chamadas_por_modelo"] == {}
        assert stats["upgrades_para_opus"] == 0


class TestEstimarTokens:
    def test_string_vazia_retorna_1_minimo(self):
        assert estimar_tokens("") == 1

    def test_4_chars_aprox_1_token(self):
        assert estimar_tokens("abcd") == 1
        assert estimar_tokens("a" * 100) == 25
