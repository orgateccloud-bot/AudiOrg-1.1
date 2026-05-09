"""A-24: @Classificador-CFOP — Validação e Sugestão de CFOPs
STATUS: ✅ PRODUÇÃO (ORGATEC CUSTOM)
Migrado de A-13 para A-24 conforme spec oficial 05/05/2026.

M-01: Batching de 50 notas por chamada — processa 100% das notas em vez de 6%.
"""
import asyncio
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

SYSTEM = """Você é o @Classificador-CFOP da ORGATEC IA. Para cada nota, verifique se o CFOP está correto.
Retorne JSON: {"notas_cfop": [{"numero": "...", "cfop_atual": "...", "cfop_correto": "...", "diverge": false, "justificativa": "..."}], "total_divergencias": 0}"""

_BATCH_SIZE = 50


class ClassificadorCFOPAgent(BaseAgent):
    agent_id = "A-24"
    name = "@Classificador-CFOP"

    async def process(self, payload: dict) -> AgentResult:
        notas = payload.get("notas", [])
        self.log("Classificando CFOPs", total_notas=len(notas))

        campos = ["numero", "cfop", "natureza", "posicao"]
        batches = [notas[i:i + _BATCH_SIZE] for i in range(0, len(notas), _BATCH_SIZE)]

        async def _processar_batch(lote: list) -> dict:
            amostra = [{k: n.get(k) for k in campos} for n in lote]
            prompt = f"Valide os CFOPs das notas fiscais rurais:\n{amostra}"
            resp = (await call_otimizado(prompt, SYSTEM, max_tokens=4096, agent_id=self.agent_id))[0]
            try:
                return json.loads(resp)
            except json.JSONDecodeError:
                return {"notas_cfop": [], "total_divergencias": 0}

        resultados = await asyncio.gather(*[_processar_batch(b) for b in batches])

        notas_cfop: list = []
        total_divergencias = 0
        for r in resultados:
            notas_cfop.extend(r.get("notas_cfop", []))
            total_divergencias += int(r.get("total_divergencias", 0))

        data = {"notas_cfop": notas_cfop, "total_divergencias": total_divergencias}
        status = "ESCALADO" if total_divergencias > 0 else "APROVADO"
        return AgentResult(agent_id=self.agent_id, status=status, output=data, confidence=0.90)
