"""A-08 @Auditor-NFA — Auditoria Qualitativa NFA-e com Regra Especial 1 + Motor OrgAudi v4.

Pipeline:
  1. Aplica Regra Especial 1 (VENDA → COMPRA para destinatário rural)
  2. Protocolo @Delta: anonimiza PII antes de enviar para Claude
  3. Claude analisa anomalias AN-01..AN-18 e estima probabilidade de autuação
  4. Valida resposta com NFAAuditSchema (Pydantic v2)
  5. Escala para A-00 @CEO se probabilidade_autuacao > 0.6
"""
import json
from typing import List
from pydantic import BaseModel, Field

from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa
from horizon_blue_one.core.privacy import anonymize_payload
from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1


class AnomaliaSchema(BaseModel):
    codigo: str
    descricao: str
    confianca: float


class NFAAuditSchema(BaseModel):
    f1_receita_imediata: float
    f2_transito: float
    f4_receita_bruta: float
    f6_despesa: float
    f5_resultado_rural: float
    funrural: float
    aliquota_funrural: float
    irpf_estimado: float
    total_notas: int
    notas_re1_aplicada: int
    probabilidade_autuacao: float = Field(..., description="0.0 a 1.0")
    desvio_mercado_cepea: float   = Field(..., description="% de desvio vs. CEPEA")
    alertas: List[str] = []
    anomalias_detectadas: List[AnomaliaSchema] = []
    recomendacao_geral: str
    proximos_passos: List[str]


SYSTEM = """Você é o @Auditor-NFA da ORGATEC IA.
Missão: auditoria qualitativa de Notas Fiscais Avulsas de produtor rural.
Identifique anomalias AN-01..AN-18 e estime a probabilidade de autuação fiscal.

- Probabilidade de Autuação: calcule com base na gravidade e recorrência das anomalias.
- Desvio de Mercado: analise se os valores unitários parecem subfaturados para a região.

Retorne APENAS o JSON conforme o schema NFAAuditSchema (sem markdown)."""


class AuditorNFAAgent(BaseAgent):
    agent_id = "A-08"
    name     = "@Auditor-NFA"

    async def process(self, payload: dict) -> AgentResult:
        notas       = payload.get("notas", [])
        contribuinte = payload.get("contribuinte", {})
        is_pj       = payload.get("is_pj", False)

        self.log("Iniciando auditoria NFA", total_notas=len(notas))

        # 1. Aplicar Regra Especial 1
        notas_classificadas = [aplicar_regra_especial_1(n) for n in notas]

        # 2. Protocolo @Delta — anonimizar PII
        payload_protegido = anonymize_payload({
            "contribuinte": contribuinte,
            "notas": notas_classificadas[:50],
            "metadata": {"regime": "PJ" if is_pj else "PF"},
        })

        # 3. Chamar Claude (com fallback determinístico se API indisponível)
        prompt = (
            f"Analise as transações rurais (DADOS PROTEGIDOS):\n"
            + json.dumps(payload_protegido, ensure_ascii=False)
        )
        try:
            resp = (await call_otimizado(prompt, SYSTEM, agent_id=self.agent_id))[0]
            data_dict = json.loads(resp)
            validated = NFAAuditSchema(**data_dict)
            status    = "ESCALADO" if validated.probabilidade_autuacao > 0.6 else "APROVADO"
            output    = validated
        except Exception as exc:
            self.log_error("Claude indisponível — usando resultado determinístico", exc=exc)
            total = len(notas_classificadas)
            re1   = sum(1 for n in notas_classificadas if n.get("regra_aplicada") == "REGRA_ESPECIAL_1")
            output = {
                "erro_claude": "API indisponível — análise qualitativa não gerada",
                "total_notas": total,
                "notas_re1_aplicada": re1,
                "probabilidade_autuacao": 0.0,
                "desvio_mercado_cepea": 0.0,
                "alertas": ["Análise Claude indisponível — resultado baseado em detectores determinísticos"],
                "anomalias_detectadas": [],
                "recomendacao_geral": "Analisar manualmente após restaurar acesso à API",
                "proximos_passos": ["Verificar crédito da API Anthropic", "Re-executar auditoria"],
            }
            status = "ERRO"

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=output,
            confidence=0.95,
        )
