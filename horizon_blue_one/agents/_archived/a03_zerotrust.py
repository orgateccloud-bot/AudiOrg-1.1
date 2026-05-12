"""A-03 @ZeroTrust — Validação de Integridade e Autenticidade Documental"""
import json
import hashlib
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @ZeroTrust da ORGATEC IA, especialista em validação documental Zero-Trust.
Verifique: assinaturas digitais, chaves de acesso NFA-e, consistência de dados entre campos.
Identifique inconsistências que indicam documentos adulterados, NFAs fantasmas ou emissões indevidas.
Retorne JSON: {"autenticidade": "VÁLIDO|SUSPEITO|INVÁLIDO", "inconsistencias": [], "score_confianca": 0.0, "acoes": []}"""


def _hash_nota(nota: dict) -> str:
    campos_chave = {k: nota.get(k) for k in ["numero", "data", "valor_total", "remetente_cpf", "destinatario_cpf"]}
    return hashlib.sha256(json.dumps(campos_chave, sort_keys=True).encode()).hexdigest()[:12]


class ZeroTrustAgent(BaseAgent):
    agent_id = "A-03"
    name = "@ZeroTrust"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Validando integridade documental Zero-Trust", total_notas=len(notas))

        inconsistencias = []
        for n in notas:
            if not n.get("numero"):
                inconsistencias.append(f"Nota sem número: {n.get('data')}")
            if float(n.get("valor_total", 0)) <= 0:
                inconsistencias.append(f"Nota {n.get('numero')} com valor inválido: {n.get('valor_total')}")
            if n.get("remetente_cpf") == n.get("destinatario_cpf"):
                inconsistencias.append(f"Nota {n.get('numero')}: remetente == destinatário (operação consigo mesmo)")

        prompt = f"""Valide a autenticidade das {len(notas)} notas fiscais.
Inconsistências detectadas automaticamente: {inconsistencias}
Dados das notas: {[{k: n.get(k) for k in ['numero','data','natureza','valor_total','cfop']} for n in notas[:10]]}"""
        resp = await call_model(ModelType.CLAUDE, prompt, SYSTEM, max_tokens=1024)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            autenticidade = "SUSPEITO" if inconsistencias else "VÁLIDO"
            data = {"autenticidade": autenticidade, "inconsistencias": inconsistencias,
                    "score_confianca": 0.5, "acoes": ["Revisão manual recomendada"]}

        status = "APROVADO" if data.get("autenticidade") == "VÁLIDO" else "ESCALADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=data.get("score_confianca", 0.85),
        )
