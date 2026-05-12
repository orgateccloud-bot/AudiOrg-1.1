"""A-Chat — Interface conversacional sobre um laudo já emitido.

Recebe o laudo (output completo do pipeline NFA-e) + histórico de perguntas
e devolve a resposta de Claude. Toda chamada passa por @Delta no BaseAgent.

Claude não recalcula valores — interpreta o que já está no laudo determinístico.
"""
import json
from typing import Any

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType

SYSTEM = """Você é o assistente OrgAudi, especialista em auditoria fiscal rural NFA-e.
Você responde perguntas do contador sobre UM laudo específico já gerado pelo motor.

Regras absolutas:
1. NUNCA recalcule Funrural, IRPF, ICMS ou qualquer tributo. Use APENAS valores
   já presentes no laudo. Se a pergunta exige cálculo novo, peça para o usuário
   rodar a auditoria novamente com os dados corretos.
2. Cite SEMPRE o campo do laudo onde está a evidência da sua resposta
   (ex: "no resumo F4, Funrural PJ = R$ 12.345").
3. Linguagem técnica mas acessível: contador, não advogado.
4. Quando relevante, referencie CTN art. 138 (denúncia espontânea) e
   anomalias AN-01..AN-18 detectadas no laudo.
5. Se a pergunta foge ao escopo deste laudo, diga "não tenho essa informação no laudo".
"""


class AChatAgent(BaseAgent):
    agent_id = "A-CHAT"
    name = "@Chat"

    async def process(self, payload: dict) -> AgentResult:
        """Espera payload: {laudo: dict, pergunta: str, historico: list[{q,r}]}."""
        pergunta = (payload.get("pergunta") or "").strip()
        if not pergunta:
            return AgentResult(
                agent_id=self.agent_id,
                status="REJEITADO",
                output={"erro": "pergunta vazia"},
                confidence=0.0,
            )

        laudo: dict[str, Any] = payload.get("laudo") or {}
        historico = payload.get("historico") or []

        # Prompt compactado: só os campos do laudo relevantes para Q&A
        laudo_compacto = {
            "veredito":       laudo.get("veredito_ia") or laudo.get("status"),
            "qtd_notas":      laudo.get("qtd_notas"),
            "valor_total":    laudo.get("valor_total"),
            "resumo_fiscal":  laudo.get("resumo_fiscal"),
            "anomalias":      laudo.get("anomalias_detectadas") or [],
            "score_xgboost":  laudo.get("score_xgboost"),
            "recomendacoes":  laudo.get("acoes_recomendadas") or [],
            "result_id":      laudo.get("result_id"),
        }

        self.log(
            "Pergunta sobre laudo",
            result_id=laudo_compacto["result_id"],
            tamanho_pergunta=len(pergunta),
            qtd_historico=len(historico),
        )

        resp = await self._call_llm(
            model_type=ModelType.HAIKU,
            prompt_payload={
                "laudo": laudo_compacto,
                "historico": historico[-5:],
                "pergunta": pergunta,
            },
            prompt_template=(
                "Contexto: {payload}\n\n"
                "Responda a pergunta acima usando APENAS o laudo. "
                "Cite o campo onde está a evidência."
            ),
            system=SYSTEM,
            max_tokens=1024,
        )

        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output={"resposta": resp.strip(), "pergunta": pergunta},
            confidence=0.85,
        )
