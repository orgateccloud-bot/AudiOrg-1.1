"""A-02 @Protetor — Segurança de Dados, LGPD e Mascaramento de PII"""
import json
import re
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType

SYSTEM = """Você é o @Protetor da ORGATEC IA, responsável por compliance LGPD e segurança de dados.
Analise payloads em busca de PII exposta (CPF, CNPJ, dados bancários não mascarados).
Verifique: bases legais para tratamento, consentimento, minimização de dados.
Retorne JSON: {"pii_detectado": bool, "campos_expostos": [], "nivel_risco_lgpd": "BAIXO|MÉDIO|ALTO|CRÍTICO", "recomendacoes": []}"""

_CPF_RE = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
_CONTA_RE = re.compile(r'\b\d{4,6}-?\d{1}\b')


class ProtetorAgent(BaseAgent):
    agent_id = "A-02"
    name = "@Protetor"

    async def process(self, payload: dict) -> AgentResult:
        self.log("Analisando payload para PII e LGPD")
        raw = json.dumps(payload, ensure_ascii=False)
        cpfs = _CPF_RE.findall(raw)
        contas = _CONTA_RE.findall(raw)
        campos_expostos = []
        if cpfs:
            campos_expostos.append(f"CPF(s) detectado(s): {len(cpfs)} ocorrência(s)")
        if contas:
            campos_expostos.append(f"Possível conta bancária: {len(contas)} ocorrência(s)")

        prompt = f"Analise a estrutura de dados para compliance LGPD:\n{list(payload.keys())}\nCampos PII detectados: {campos_expostos}"
        resp = await call_model(ModelType.SONNET, prompt, SYSTEM, max_tokens=1024)
        try:
            data = json.loads(resp)
        except json.JSONDecodeError:
            data = {"pii_detectado": bool(campos_expostos), "campos_expostos": campos_expostos,
                    "nivel_risco_lgpd": "MÉDIO", "recomendacoes": ["Revisar mascaramento de CPF"]}

        status = "APROVADO" if not data.get("pii_detectado") else "ESCALADO"
        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=0.90,
        )
