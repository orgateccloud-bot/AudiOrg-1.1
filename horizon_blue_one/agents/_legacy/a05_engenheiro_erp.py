"""A-05 @Engenheiro-ERP — Integração e Extração de Dados de ERPs Rurais"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Engenheiro-ERP da ORGATEC IA, especialista em integração com sistemas ERP rurais.
Sistemas suportados: Rural Soft, AgroNote, FazendaPro, QualiAgro, Siagri, Controlsys.
Extraia: plano de contas, lançamentos contábeis, movimentações de estoque e folha rural.
Normalize para o padrão ORGATEC e identifique inconsistências com SPED/LCDPR.
Retorne JSON: {"sistema_erp": "...", "lancamentos": [], "divergencias_sped": [], "status_integracao": "OK|PARCIAL|ERRO"}"""


class EngenheiroERPAgent(BaseAgent):
    agent_id = "A-05"
    name = "@Engenheiro-ERP"

    async def process(self, payload: dict) -> AgentResult:
        dados_erp = payload.get("dados_erp", {})
        sistema = payload.get("sistema_erp", "desconhecido")
        self.log("Integrando dados de ERP", sistema=sistema)

        prompt = f"""Normalize os dados do ERP {sistema} para o padrão ORGATEC:
{json.dumps(dados_erp, ensure_ascii=False, indent=2)[:3000]}

Identifique divergências com SPED ECF, EFD e LCDPR.
Mapeie contas para plano ORGATEC (1.x Ativo, 2.x Passivo, 3.x Receita, 4.x Despesa)."""

        resp = (await call_otimizado(prompt, max_tokens=4096, agent_id=self.agent_id))[0]
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"sistema_erp": sistema, "lancamentos": [], "divergencias_sped": [],
                    "status_integracao": "PARCIAL", "raw": resp[:500]}

        status = "APROVADO" if data.get("status_integracao") == "OK" else "ESCALADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.85,
        )
