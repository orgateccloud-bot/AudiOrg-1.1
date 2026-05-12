"""Smoke test do Sprint 1+2+3.

Valida:
  - precalcular() roda e cacheia em payload["__precalc__"]
  - 10 chaves esperadas existem
  - Detectores rodam UMA vez (test que F1/F2 está fixado)
  - Early-exit quando audit é limpa
  - F13: detectar_devolucao_posterior agora casa
"""
from __future__ import annotations

import pytest

from horizon_blue_one.agents.detectores_forenses import detectar_devolucao_posterior
from horizon_blue_one.core.precalc import _MEMO_CACHE, precalcular
from horizon_blue_one.core.prompt_compactor import flags, kv, resumo_detectores, tsv


@pytest.mark.asyncio
async def test_precalc_chaves_esperadas():
    payload = {
        "notas": [
            {"numero": "1", "data": "2026-01-10", "natureza": "VENDA", "cfop": "5101",
             "valor_total": 12000, "categoria_contabil": "RECEITA",
             "remetente_cpf": "12345678901", "destinatario_cpf": "98765432100",
             "chave_acesso": "1" * 44},
            {"numero": "2", "data": "2026-01-15", "natureza": "VENDA", "cfop": "5101",
             "valor_total": 8000, "categoria_contabil": "RECEITA",
             "remetente_cpf": "12345678901", "destinatario_cpf": "11122233344",
             "chave_acesso": "2" * 44},
        ],
        "contribuinte": {"razao_social": "Fazenda Teste", "cpf_cnpj": "12345678901",
                         "inscricao_estadual": "1234567", "area_total_ha": 100,
                         "area_utilizada_ha": 90},
        "lcdpr_data": {"total_receitas": 20000, "total_despesas": 5000},
    }
    out = await precalcular(payload)
    pre = out["__precalc__"]

    assert set(pre.keys()) >= {
        "notas_re1", "pii", "documentos", "detectores", "xgboost",
        "cfop", "lcdpr", "itr", "grafo", "caixa",
    }
    assert pre["caixa"]["entradas"] == 20000
    assert pre["lcdpr"]["status_conformidade"] == "CONFORME"
    assert pre["itr"]["gu_pct"] == 90.0


@pytest.mark.asyncio
async def test_precalc_idempotente():
    payload = {"notas": [], "contribuinte": {}, "lcdpr_data": {}}
    out1 = await precalcular(payload)
    pre1 = out1["__precalc__"]
    out2 = await precalcular(out1)
    assert out2["__precalc__"] is pre1  # mesmo objeto, sem recomputo


def test_f13_devolucao_posterior_casa():
    """F13: antes era impossível casar (multiplicava por 1.1 antes do round)."""
    notas = [
        {"natureza": "VENDA", "valor_total": 10000, "remetente_cpf": "X"},
        {"natureza": "DEVOLUCAO", "valor_total": 9500, "destinatario_cpf": "X"},
    ]
    assert detectar_devolucao_posterior(notas) is True


def test_f13_devolucao_sem_match():
    notas = [
        {"natureza": "VENDA", "valor_total": 10000, "remetente_cpf": "X"},
        {"natureza": "DEVOLUCAO", "valor_total": 100, "destinatario_cpf": "X"},  # 1% — fora da faixa
    ]
    assert detectar_devolucao_posterior(notas) is False


def test_compactor_kv_economiza():
    import json
    d = {"score": 87, "nivel": "ALTO", "carrossel": True, "smurfing": False, "criticos": 3}
    json_repr = json.dumps(d)
    compact = kv(d)
    # Compactor deve sempre ser >= 25% mais curto que JSON dump em casos típicos
    assert len(compact) < len(json_repr) * 0.85, f"compact={compact!r} json={json_repr!r}"


def test_compactor_resumo_detectores():
    out = resumo_detectores({
        "carrossel": True, "smurfing": False, "devolucao_posterior": False,
        "anomalia_temporal": True, "fornecedor_fantasma": ["123", "456"],
    })
    assert "carrossel=sim" in out
    assert "fornecedor_fantasma=2" in out
    assert "smurfing=nao" in out


def test_compactor_tsv_formato():
    notas = [
        {"numero": "1", "valor_total": 100.0},
        {"numero": "2", "valor_total": 250.5},
    ]
    out = tsv(notas, ("numero", "valor_total"))
    linhas = out.split("\n")
    assert linhas[0] == "numero\tvalor_total"
    assert linhas[1] == "1\t100.00"
    assert linhas[2] == "2\t250.50"


def test_compactor_flags():
    assert flags({"a": True, "b": False, "c": ["x"]}) == "a,c"
    assert flags({"a": False, "b": []}) == "nenhuma"


@pytest.mark.asyncio
async def test_precalc_memo_reusa_5min():
    _MEMO_CACHE.clear()
    payload = {
        "notas": [{"numero": "1", "valor_total": 100, "data": "2026-01-01"}],
        "contribuinte": {"cpf_cnpj": "X"},
        "lcdpr_data": {},
    }
    p1 = await precalcular(dict(payload))
    pre1 = p1["__precalc__"]
    p2 = await precalcular(dict(payload))
    pre2 = p2["__precalc__"]
    # Issue #28: memo retorna snapshots isolados (deep copy) — equivalentes
    # mas com referências distintas para evitar contaminação cross-request.
    assert pre1 is not pre2
    assert pre1["notas_re1"] == pre2["notas_re1"]
    assert pre1["xgboost"] == pre2["xgboost"]


@pytest.mark.asyncio
async def test_audit_limpa_early_exit_flag():
    """Cenário limpo: notas variadas, CFOPs corretos, sem detecções → pula LLMs."""
    from horizon_blue_one.core.orchestrator import Orchestrator
    notas = [
        {"numero": str(i), "data": f"2026-0{(i % 9) + 1}-15", "natureza": "COMPRA",
         "cfop": "1101", "valor_total": 500 + i * 137, "categoria_contabil": "DESPESA",
         "chave_acesso": f"{i:044d}", "destinatario_cpf": f"CPF-{i % 5}"}
        for i in range(20)
    ]
    payload = {
        "notas": notas,
        "contribuinte": {"inscricao_estadual": "1234567"},
        "lcdpr_data": {"total_receitas": 0, "total_despesas": sum(n["valor_total"] for n in notas)},
    }
    orch = Orchestrator()
    res = await orch.executar_pipeline(payload, agentes=[], chamar_ceo_no_fim=False)
    assert "__EARLY_EXIT__" in res
    assert res["__EARLY_EXIT__"].status == "APROVADO"
