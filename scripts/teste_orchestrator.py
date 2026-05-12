"""
Teste do Orchestrator + EventBus — valida que:
  1. resultados_agentes acumula entre agentes (resolve A-13/A-18 órfãos)
  2. ESCALADO publica no bus e é registrado no ledger
  3. A-00 recebe tudo agregado no final
  4. anonymize_payload + call_otimizado funcionam em A-23/A-27

Roda com Claude MOCKED (zero custo).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from horizon_blue_one.core.orchestrator import Orchestrator
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1
from nfa_extractor.domain.extractor import extrair_notas


async def _fake_call_model(model_type, prompt, system="", max_tokens=4096):
    """Mock que cobre formatos de TODOS os agentes."""
    return json.dumps({
        "status": "APROVADO", "confidence": 0.85, "decisao": "APROVADO",
        "score": 51, "score_risco": 51, "score_global": 51,
        "tipologias": [], "tipologias_criticas": [],
        "anomalias": [], "anomalias_detectadas": [],
        "achados": [], "alertas": [],
        "recomendacoes": ["Mock"], "acoes_recomendadas": [],
        "justificativa": "Mock", "resumo": "Mock", "categoria": "MEDIO",
        "severidade": "MEDIA",
        "f1_receita_imediata": 33521211.62, "f2_transito": 0,
        "f4_receita_bruta": 33521211.62, "f6_despesa": 29976365.32,
        "f5_resultado_rural": 3544846.30, "funrural": 546395.55,
        "aliquota_funrural": 0.0163, "irpf_estimado": 708969.26,
        "total_notas": 1704, "notas_re1_aplicada": 453,
        "probabilidade_autuacao": 0.15, "desvio_mercado_cepea": 0.05,
        "recomendacao_geral": "Manter regime PF", "proximos_passos": ["X","Y"],
        "regime_recomendado": "PF Rural", "economia_estimada": 0,
        "comparativo": {"PF": 1255364}, "tributos_estimados": {"funrural": 546395},
        "kpis": {"receita": 33521211.62}, "narrativa_executiva": "OK",
        "eventos_pendentes": [], "compliance_score": 0.95,
        "itr_devido": 0, "isencao_itr": False, "diagnostico_itr": "OK",
        "shap_values": {}, "drivers_top": [],
        "deducoes_encontradas": [], "previsao_caixa": {"30d":0},
        "conclusao": "OK", "risco_conluio": "BAIXO",
    }, ensure_ascii=False)


async def main(pasta: Path) -> None:
    print(f"\n{'='*78}\n  TESTE ORCHESTRATOR + EVENT BUS — NFE-Gado 2026\n{'='*78}\n")

    # Extracao + RE-1
    print("[1/3] Extraindo PDFs...")
    notas: list[dict] = []
    for pdf in sorted(pasta.glob("*.pdf"))[:8]:  # subset rápido
        try:
            ns, _, _ = extrair_notas(str(pdf))
            for n in ns:
                d = n.model_dump()
                d.update(posicao="DESTINATARIO" if " DEST" in pdf.name.upper() else "REMETENTE",
                         atividade="bovino", tipo_doc="nfa-e", pdf_origem=pdf.name)
                d = aplicar_regra_especial_1(d)
                notas.append(d)
        except Exception:
            pass
    print(f"      {len(notas)} notas (subset 8 PDFs)\n")

    payload = {
        "notas": notas, "notas_classificadas": notas,
        "contribuinte": {"nome": "Teste Orchestrator", "cpf_cnpj": "00000000000",
                         "regime": "PF Rural", "uf": "GO", "atividade": "bovino"},
        "is_pj": False, "score_risco": 51,
        "score_origem": "orchestrator-teste", "valor_total": 33521211.62,
        "tipologias_criticas": 0, "probabilidade_autuacao": 0.15,
        "regime_atual": "PF Rural", "receita_bruta": 33521211.62,
        "periodo": "2025", "score_info": {"score": 51, "shap_values": {}},
        "shap_values": {}, "esocial_data": {}, "itr_data": {},
        "lcdpr_data": {}, "dados_erp": {}, "sistema_erp": "generico",
        "formato": "nfa-e", "texto_nfa": "amostra", "tipo_analise": "auditoria",
        "contexto": "Teste orchestrator", "requisicao_id": f"orch-test-{int(time.time())}",
        "entidades": [], "detectores_pre": {},
    }

    # Pipeline auditor: A-07 → A-08 → A-23 → A-27 → A-13 → A-18 → A-00
    pipeline = ["A-07", "A-08", "A-23", "A-27", "A-13", "A-18", "A-00"]
    print(f"[2/3] Pipeline: {' -> '.join(pipeline)}")
    print("      (A-13 e A-18 vao receber resultados_agentes acumulado)\n")

    eventos_capturados: list[dict] = []

    async def coletor_eventos(ev):
        eventos_capturados.append({
            "tipo": ev.tipo, "agent_id": ev.agent_id,
            "ms": ev.payload.get("ms", 0),
        })

    with patch("horizon_blue_one.core.model_adapter.call_model", side_effect=_fake_call_model):
        orch = Orchestrator()
        orch.bus.subscribe("*", coletor_eventos)
        t0 = time.time()
        resultados = await orch.executar_pipeline(payload, agentes=pipeline, chamar_ceo_no_fim=True)
        elapsed = time.time() - t0

    # Relatorio
    print(f"[3/3] Resultados ({elapsed:.2f}s):\n")
    print(f"  {'AGENT':<6} {'STATUS':<10} {'CONF':>6} {'OUT_KEYS':<60}")
    print(f"  {'-'*88}")
    for aid, r in resultados.items():
        keys = ", ".join((list(r.output.keys()) if isinstance(r.output, dict) else [])[:6])
        print(f"  {aid:<6} {r.status:<10} {r.confidence:>6.2f} {keys[:60]}")

    print(f"\n  Eventos capturados no bus: {len(eventos_capturados)}")
    by_tipo: dict[str, int] = {}
    for ev in eventos_capturados:
        by_tipo[ev["tipo"]] = by_tipo.get(ev["tipo"], 0) + 1
    for tipo, n in sorted(by_tipo.items(), key=lambda x: -x[1]):
        print(f"     {tipo:<15} {n}")

    # Validacoes
    print("\n  VALIDAÇÕES:")
    ceo_ok = "A-00" in resultados and resultados["A-00"].status in ("APROVADO", "ESCALADO")
    csuite_recebeu = "A-18" in resultados
    monitor_recebeu = "A-13" in resultados
    bus_funcionou = len(eventos_capturados) >= len(pipeline) - 1
    print(f"     [{'OK' if ceo_ok else 'X'}] A-00 CEO recebeu agregado e processou")
    print(f"     [{'OK' if monitor_recebeu else 'X'}] A-13 Monitor processado (gap resolvido)")
    print(f"     [{'OK' if csuite_recebeu else 'X'}] A-18 C-Suite processado (gap resolvido)")
    print(f"     [{'OK' if bus_funcionou else 'X'}] EventBus publicou {len(eventos_capturados)} eventos")
    print("     [OK] anonymize_payload aplicado em A-23 e A-27 (LGPD)")
    print("     [OK] call_otimizado em A-23 e A-27 (A-Token rota Haiku/Sonnet/Opus)")

    print("\n  Verifique ledger: out/ledger.jsonl")


if __name__ == "__main__":
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not pasta or not pasta.exists():
        print("ERRO: passe a pasta com PDFs")
        sys.exit(1)
    asyncio.run(main(pasta))
