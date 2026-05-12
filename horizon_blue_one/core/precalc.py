"""
horizon_blue_one/core/precalc.py - Pre-calculo de payload S1-S7.
SEGURANCA: deep copy garante isolamento entre coroutines concorrentes.
"""
from __future__ import annotations
import copy
from typing import Any

def precalc(payload: dict[str, Any]) -> dict[str, Any]:
    """Popula payload['precalc'] com metricas derivadas das notas.
    Retorna deep copy - nunca modifica o objeto original.
    """
    payload = copy.deepcopy(payload)
    notas: list[dict] = payload.get("notas", [])
    total_notas = len(notas)
    valor_total = sum(float(n.get("valor_total", 0)) for n in notas)
    valor_medio = valor_total / total_notas if total_notas else 0.0
    cfops = [n.get("cfop", "") for n in notas if n.get("cfop")]
    cfop_predominante = max(set(cfops), key=cfops.count) if cfops else ""
    naturezas: dict[str, int] = {}
    for n in notas:
        nat = (n.get("natureza") or "").upper()
        if nat:
            naturezas[nat] = naturezas.get(nat, 0) + 1
    destinatarios = [n.get("destinatario_cpf", "") for n in notas if n.get("destinatario_cpf")]
    dest_unicos = len(set(destinatarios))
    concentracao = (max(destinatarios.count(d) / total_notas for d in set(destinatarios)) if destinatarios else 0.0)
    payload["precalc"] = {
        "total_notas": total_notas, "valor_total": round(valor_total, 2),
        "valor_medio": round(valor_medio, 2), "cfop_predominante": cfop_predominante,
        "naturezas": naturezas, "destinatarios_unicos": dest_unicos,
        "concentracao_destinatario": round(concentracao, 4),
    }
    return payload
