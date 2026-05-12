"""Testes da calibração contínua (F4)."""
from __future__ import annotations

import pytest

from horizon_blue_one.core.calibracao import (
    MIX_ALVO_PCT,
    Recomendacao,
    _rec_dict,
    analisar_routing_mix,
    analisar_saturacao,
    analisar_thresholds_escalada,
    relatorio_calibracao,
)


def _snapshot(haiku=0, sonnet=0, opus=0, upgrades=0, downgrades=0):
    chamadas = {}
    if haiku:  chamadas["haiku"]  = haiku
    if sonnet: chamadas["sonnet"] = sonnet
    if opus:   chamadas["opus"]   = opus
    return {
        "chamadas":   chamadas,
        "upgrades":   upgrades,
        "downgrades": downgrades,
    }


# ── Mix observado vs alvo 90/8/2 ──────────────────────────────────────────────

class TestAnalisarMix:
    def test_sem_chamadas_emite_info(self):
        recs = analisar_routing_mix({"chamadas": {}})
        assert len(recs) == 1
        assert recs[0].severidade == "info"
        assert "Sem chamadas" in recs[0].mensagem

    def test_mix_dentro_da_tolerancia(self):
        # 90/8/2 exato — dentro da tolerância
        recs = analisar_routing_mix(_snapshot(haiku=90, sonnet=8, opus=2))
        assert len(recs) == 1
        assert recs[0].severidade == "info"

    def test_haiku_muito_abaixo_alerta_critico(self):
        # 30% Haiku (alvo 90%) → delta -60% → critico
        recs = analisar_routing_mix(_snapshot(haiku=30, sonnet=50, opus=20))
        criticos = [r for r in recs if r.severidade == "critico"]
        assert any("haiku" in r.detalhes["modelo"] for r in criticos)

    def test_opus_muito_acima_critico(self):
        # 30% Opus (alvo 2%)
        recs = analisar_routing_mix(_snapshot(haiku=50, sonnet=20, opus=30))
        opus_recs = [r for r in recs if r.detalhes.get("modelo") == "opus"]
        assert opus_recs and opus_recs[0].severidade in ("atencao", "critico")

    def test_pequeno_desvio_atencao(self):
        # 80% Haiku (alvo 90%) → delta -10% → atencao
        recs = analisar_routing_mix(_snapshot(haiku=80, sonnet=18, opus=2))
        h_rec = next(r for r in recs if r.detalhes.get("modelo") == "haiku")
        assert h_rec.severidade == "atencao"


# ── Saturação por agente ──────────────────────────────────────────────────────

class TestAnalisarSaturacao:
    def test_p95_alto_recomenda_subir_max_tokens(self):
        # 20 observações ≥ 0.96 → p95 alto
        obs = {"S2": [0.96] * 20}
        recs = analisar_saturacao(obs)
        criticos = [r for r in recs if r.severidade == "critico"]
        assert criticos
        assert "S2" in criticos[0].mensagem
        assert criticos[0].detalhes["p95"] >= 0.95

    def test_media_baixa_recomenda_reduzir(self):
        # Todos abaixo de 0.20 → over-allocation
        obs = {"A-01": [0.05] * 30}
        recs = analisar_saturacao(obs)
        infos = [r for r in recs if r.detalhes.get("agente") == "A-01"]
        assert infos
        assert "over-allocation" in infos[0].mensagem

    def test_saturacao_saudavel_emite_info(self):
        # 50% saturação média, p95 = 0.6 — banda OK
        obs = {"A-07": [0.4, 0.5, 0.6, 0.5, 0.4]}
        recs = analisar_saturacao(obs)
        assert len(recs) == 1
        assert recs[0].severidade == "info"
        assert "saudáveis" in recs[0].mensagem

    def test_dict_vazio_emite_info(self):
        recs = analisar_saturacao({})
        assert len(recs) == 1 and recs[0].severidade == "info"

    def test_agente_sem_observacoes_ignorado(self):
        obs = {"A-01": [], "S2": [0.96] * 20}
        recs = analisar_saturacao(obs)
        # Apenas S2 gera alerta
        assert any("S2" in r.mensagem for r in recs if r.severidade == "critico")


# ── Thresholds de escalada ────────────────────────────────────────────────────

class TestAnalisarThresholds:
    def test_volume_baixo_emite_info(self):
        recs = analisar_thresholds_escalada(_snapshot(haiku=10, sonnet=5))
        assert recs[0].severidade == "info"
        assert "Volume baixo" in recs[0].mensagem

    def test_upgrades_excessivos_atencao(self):
        # 10 upgrades / 100 chamadas = 10% (alvo ~2%)
        recs = analisar_thresholds_escalada(
            _snapshot(haiku=90, sonnet=8, opus=2, upgrades=10),
        )
        ats = [r for r in recs if r.severidade == "atencao"]
        assert ats and "Upgrades para Opus" in ats[0].mensagem

    def test_zero_upgrades_em_volume_grande_emite_info(self):
        recs = analisar_thresholds_escalada(
            _snapshot(haiku=200, sonnet=20, upgrades=0),
        )
        infos = [r for r in recs if "Threshold" in r.mensagem]
        assert infos

    def test_downgrades_muitos_emite_info_saude(self):
        # 60 downgrades / 100 = 60% — política agressiva, mas custo OK
        recs = analisar_thresholds_escalada(
            _snapshot(haiku=100, downgrades=60),
        )
        infos = [r for r in recs if "Downgrades" in r.mensagem]
        assert infos and infos[0].severidade == "info"

    def test_dentro_do_esperado(self):
        # 2 upgrades / 100 = 2% (alvo)
        recs = analisar_thresholds_escalada(
            _snapshot(haiku=90, sonnet=8, opus=2, upgrades=2),
        )
        # Nenhum critico/atencao — só info "Escaladas dentro do esperado"
        assert all(r.severidade == "info" for r in recs)


# ── Relatório consolidado ─────────────────────────────────────────────────────

class TestRelatorioCalibracao:
    def test_estrutura_completa(self):
        snap = _snapshot(haiku=90, sonnet=8, opus=2)
        rel = relatorio_calibracao(snap)
        assert set(rel.keys()) == {"mix", "saturacao", "thresholds", "resumo"}
        for k in ("n_criticos", "n_atencao", "n_info"):
            assert k in rel["resumo"]

    def test_resumo_conta_severidades(self):
        # Mix muito ruim → critico
        snap = _snapshot(haiku=30, sonnet=50, opus=20, upgrades=20)
        obs = {"S2": [0.97] * 20}
        rel = relatorio_calibracao(snap, observacoes_por_agente=obs)
        assert rel["resumo"]["n_criticos"] >= 1
        # Pelo menos 1 atencao (upgrades excessivos = 20%)
        assert rel["resumo"]["n_atencao"] >= 1

    def test_sem_observacoes_default_dict_vazio(self):
        rel = relatorio_calibracao(_snapshot(haiku=90, sonnet=8, opus=2))
        # observacoes_por_agente omitido → análise de saturação emite info
        assert rel["saturacao"][0]["severidade"] == "info"

    def test_recomendacao_serializa_para_dict(self):
        r = Recomendacao(
            categoria="mix", severidade="info",
            mensagem="ok", detalhes={"x": 1},
        )
        d = _rec_dict(r)
        assert d == {
            "categoria": "mix", "severidade": "info",
            "mensagem": "ok", "detalhes": {"x": 1},
        }


def test_mix_alvo_soma_um():
    """Sanidade: alvos somam 100%."""
    assert sum(MIX_ALVO_PCT.values()) == pytest.approx(1.0)
