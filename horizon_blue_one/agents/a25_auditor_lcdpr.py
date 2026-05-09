"""A-25: @Auditor-LCDPR — Livro Caixa Digital do Produtor Rural
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM)
Migrado de A-14 para A-25 conforme spec oficial 05/05/2026.
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Auditor-LCDPR da ORGATEC IA, especialista no Livro Caixa Digital do Produtor Rural.
Retorne JSON: {"saldo_lcdpr": 0.0, "receitas_nao_declaradas": 0.0, "despesas_sem_comprovante": 0.0, "alertas": [], "status_conformidade": "CONFORME|DIVERGENTE|CRÍTICO"}"""


class AuditorLCDPRAgent(BaseAgent):
    agent_id = "A-25"
    name = "@Auditor-LCDPR"

    async def process(self, payload: dict) -> AgentResult:
        lcdpr = payload.get("lcdpr_data", {})
        notas = payload.get("notas", [])
        self.log("Auditando LCDPR", total_notas=len(notas))
        total_notas_receita = sum(float(n.get("valor_total", 0))
                                  for n in notas if n.get("categoria_contabil") == "RECEITA")
        lcdpr_receita = float(lcdpr.get("total_receitas", 0))
        divergencia = abs(total_notas_receita - lcdpr_receita)
        prompt = f"""Audite o LCDPR:
- Receita NFA-e: R$ {total_notas_receita:,.2f} | LCDPR: R$ {lcdpr_receita:,.2f} | Divergência: R$ {divergencia:,.2f}
Identifique omissões (AN-12) e despesas sem NFA-e correspondente."""
        resp = (await call_otimizado(prompt, SYSTEM, max_tokens=2048, agent_id=self.agent_id))[0]
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            status_conf = "CRÍTICO" if divergencia > 50000 else "DIVERGENTE" if divergencia > 0 else "CONFORME"
            data = {"saldo_lcdpr": lcdpr_receita - float(lcdpr.get("total_despesas", 0)),
                    "receitas_nao_declaradas": max(0, total_notas_receita - lcdpr_receita),
                    "alertas": [], "status_conformidade": status_conf}
        status = "ESCALADO" if data.get("status_conformidade") == "CRÍTICO" else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data, confidence=0.89)
