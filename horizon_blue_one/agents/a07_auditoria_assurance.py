"""A-07 @Auditoria-Assurance — Testes Forenses Determinísticos + Score XGBoost + Claude.

Pipeline:
  1. 5 detectores determinísticos locais (sem IA, sem deps externas)
  2. Score XGBoost (heurístico ou modelo treinado)
  3. Análise qualitativa via Claude (explica os padrões encontrados)
  4. Escalação automática para A-00 @CEO se score > 80 ou fornecedor fantasma
"""
import json
import structlog

from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.agents.detectores_forenses import (
    detectar_carrossel,
    detectar_smurfing,
    detectar_fornecedor_fantasma,
    detectar_devolucao_posterior,
    detectar_anomalia_temporal,
)
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa
from horizon_blue_one.ml.xgboost_scorer import calcular_score

logger = structlog.get_logger()

SYSTEM = """Você é o @Auditoria-Assurance da ORGATEC IA, especialista em testes forenses fiscais.
Analise os padrões detectados e as features de risco para identificar:
1. CARROSSEL_FISCAL — valores iguais repetidos, datas espaçadas regularmente, mesmo CFOP
2. SMURFING_RURAL — múltiplas operações pequenas no mesmo período, mesmos fornecedores
3. FORNECEDOR_FANTASMA — CNPJ/CPF sem histórico, IE inativa, endereço inconsistente
4. DEVOLUCAO_POSTERIOR — NFA-e de venda seguida de devolução parcial formando carrossel
5. CFOP_IRREGULAR — CFOP inconsistente com natureza declarada da operação
6. ANOMALIA_TEMPORAL — valores fora de 2σ do histórico, datas atípicas

Retorne APENAS o JSON:
{
  "score_risco": 0,
  "probabilidade_fraude": 0.0,
  "padroes_detectados": [],
  "recomendacao": "OK|REVISAO|AUDITORIA_URGENTE",
  "criticidade": "BAIXA|MÉDIA|ALTA|CRÍTICA",
  "proximos_passos": [],
  "confianca": 0.0
}"""

THRESHOLD_ESCALAR = 80


class AuditoriaAssuranceAgent(BaseAgent):
    agent_id = "A-07"
    name     = "@Auditoria-Assurance"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Iniciando testes forenses", total_notas=len(notas))

        # ── Detectores determinísticos ────────────────────────────────────────
        padroes_pre: list[str] = []
        if detectar_carrossel(notas):
            padroes_pre.append("CARROSSEL_FISCAL")
        if detectar_smurfing(notas):
            padroes_pre.append("SMURFING_RURAL")
        fantasmas = detectar_fornecedor_fantasma(notas)
        if fantasmas:
            padroes_pre.append("FORNECEDOR_FANTASMA")
        if detectar_devolucao_posterior(notas):
            padroes_pre.append("DEVOLUCAO_POSTERIOR")
        if detectar_anomalia_temporal(notas):
            padroes_pre.append("ANOMALIA_TEMPORAL")

        # ── Score XGBoost ────────────────────────────────────────────────────
        score_info = calcular_score(notas)
        self.log("Detecção concluída", padroes=padroes_pre, score=score_info["score"])

        # ── Análise qualitativa via Claude ───────────────────────────────────
        top10 = sorted(notas, key=lambda x: float(x.get("valor_total", 0)), reverse=True)[:10]
        prompt = (
            f"Analise {len(notas)} notas fiscais rurais.\n"
            f"Score XGBoost: {score_info['score']} | Nível: {score_info['nivel']}\n"
            f"SHAP values: {score_info['shap_values']}\n"
            f"Padrões pré-detectados: {padroes_pre}\n"
            f"Fornecedores suspeitos: {fantasmas[:10]}\n"
            f"Top-10 maiores notas: "
            + str([{k: n.get(k) for k in ["numero", "data", "valor_total", "cfop", "natureza"]}
                   for n in top10])
        )

        try:
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=2048, agent_id=self.agent_id))[0]
            data = json.loads(resp)
        except Exception:
            score = score_info["score"]
            resp  = None
            data  = None

        if data is None:
            score = score_info["score"]
            data = {
                "score_risco": score,
                "probabilidade_fraude": round(score / 100, 2),
                "padroes_detectados": list(set(padroes_pre)),
                "recomendacao": (
                    "AUDITORIA_URGENTE" if padroes_pre else
                    "REVISAO" if score > 40 else "OK"
                ),
                "criticidade": (
                    "CRÍTICA" if score > 80 else
                    "ALTA"   if score > 60 else
                    "MÉDIA"  if score > 30 else "BAIXA"
                ),
                "proximos_passos": (
                    ["Verificar fornecedores suspeitos", "Cruzar SEFAZ-GO"]
                    if padroes_pre else []
                ),
                "confianca": 0.75,
            }

        padroes_final = list(set(data.get("padroes_detectados", []) + padroes_pre))
        data["padroes_detectados"] = padroes_final
        data["score_xgboost"]      = score_info
        data["alertas"] = [f"FORENSE: {p}" for p in padroes_final]

        score_final   = data.get("score_risco", score_info["score"])
        deve_escalar  = score_final > THRESHOLD_ESCALAR or bool(fantasmas)
        status        = "ESCALADO" if deve_escalar else "APROVADO"

        if deve_escalar:
            self.log("Escalando para A-00 @CEO", score=score_final, padroes=padroes_final)

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=data.get("confianca", 0.80),
        )
