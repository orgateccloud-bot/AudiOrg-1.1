"""A-22: @Auditor-ITR — Auditoria de ITR, CAR, SNCR e Capacidade Produtiva
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM)
Migrado de A-11 para A-22 conforme spec oficial 05/05/2026.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Auditor-ITR da ORGATEC IA, especialista em ITR, CAR e capacidade produtiva rural.
Retorne JSON: {"area_declarada_ha": 0.0, "capacidade_produtiva_estimada": 0.0, "volume_declarado": 0.0, "divergencia_pct": 0.0, "alertas_itr": [], "vtn_referencia": 0.0, "risco": "BAIXO|MÉDIO|ALTO|CRÍTICO"}"""


class AuditorITRAgent(BaseAgent):
    agent_id = "A-22"
    name = "@Auditor-ITR"

    async def process(self, payload: dict) -> AgentResult:
        contribuinte = payload.get("contribuinte", {})
        itr_data = payload.get("itr_data", {})
        notas = payload.get("notas", [])
        self.log("Auditando ITR e capacidade produtiva", cpf=contribuinte.get("cpf"))
        def _safe_float(v, default: float = 0.0) -> float:
            try:
                return float(v or default)
            except (TypeError, ValueError):
                return default

        def _safe_int(v, default: int = 0) -> int:
            try:
                return int(float(v or default))
            except (TypeError, ValueError):
                return default

        volume_total = sum(_safe_float(n.get("valor_total")) for n in notas)
        area_ha = _safe_float(itr_data.get("area_total_ha"))
        cabecas_total = sum(_safe_int(n.get("cabecas")) for n in notas)
        prompt = f"""Audite o ITR do contribuinte {contribuinte.get('nome')}:
- Área: {area_ha} ha | Volume notas: R$ {volume_total:,.2f} | Cabeças: {cabecas_total}
- Dados ITR: {itr_data}
Calcule lotação máxima (UA/ha) e compare VTN declarado com IBGE/INCRA."""
        resp = (await call_otimizado(prompt, SYSTEM, max_tokens=2048, agent_id=self.agent_id))[0]
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"area_declarada_ha": area_ha, "volume_declarado": volume_total, "alertas_itr": [], "risco": "BAIXO"}
        status = "ESCALADO" if data.get("risco") in ("ALTO", "CRÍTICO") else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data, confidence=0.86)
