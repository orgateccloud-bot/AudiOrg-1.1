"""A-Narrative — Narrativa técnica do laudo (Fase 4).

Recebe achados estruturados (resumo F1-F6, anomalias AN, score XGBoost) e
devolve 3 parágrafos em pt-BR técnico-jurídico para inclusão na seção
narrativa do PDF do laudo.

Princípios:
- Claude NUNCA cita valores monetários que não estejam no laudo.
- Sem promessa de regularização sem CTN art. 138 explicitamente citado.
- Tom: informativo para o cliente, defensável para a SEFAZ-GO.
"""
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType

SYSTEM = """Você é o @Narrative do OrgAudi.

Sua tarefa: escrever a seção narrativa de UM laudo de auditoria fiscal rural NFA-e.
Estrutura obrigatória (3 parágrafos, separados por linha em branco):

[Parágrafo 1] Contexto: nome do produtor (já anonimizado), período auditado,
              volume de notas processadas, veredito sintético.
[Parágrafo 2] Achados: principais anomalias AN-XX detectadas com evidências
              objetivas; cite o score XGBoost se relevante (> 65).
[Parágrafo 3] Recomendações: ações específicas (não genéricas) por anomalia,
              com referência ao CTN art. 138 quando for caso de denúncia
              espontânea aplicável.

Regras absolutas:
- NUNCA cite valores monetários que não estejam no payload recebido.
- NUNCA prometa "regularização garantida". Use linguagem condicional.
- NUNCA mencione nomes ou CPFs reais — eles já foram redigidos.
- Português técnico-jurídico mas sem juridiquês — contador-padrão lê.
- Máximo 600 palavras no total.

Devolva JSON: {"narrativa": "...", "palavras_chave": [...], "tom": "informativo|critico|alerta"}
"""


class ANarrativeAgent(BaseAgent):
    agent_id = "A-NARRATIVE"
    name = "@Narrative"

    async def process(self, payload: dict) -> AgentResult:
        """Espera payload: dados consolidados do laudo emitido."""
        if not payload.get("resumo_fiscal") and not payload.get("anomalias_detectadas"):
            return AgentResult(
                agent_id=self.agent_id,
                status="REJEITADO",
                output={"erro": "payload sem dados de laudo"},
                confidence=0.0,
            )

        self.log(
            "Gerando narrativa",
            qtd_anomalias=len(payload.get("anomalias_detectadas") or []),
            score=payload.get("score_xgboost", {}).get("score") if isinstance(payload.get("score_xgboost"), dict) else None,
        )

        # Sonnet para narrativa: precisa de boa redação em pt-BR técnico
        resp = await self._call_llm(
            model_type=ModelType.SONNET,
            prompt_payload={
                "periodo":          payload.get("periodo"),
                "qtd_notas":        payload.get("qtd_notas"),
                "valor_total":      payload.get("valor_total"),
                "veredito":         payload.get("veredito_ia"),
                "resumo_fiscal":    payload.get("resumo_fiscal"),
                "anomalias":        payload.get("anomalias_detectadas") or [],
                "score_xgboost":    payload.get("score_xgboost"),
                "acoes_sugeridas":  payload.get("acoes_recomendadas") or [],
            },
            prompt_template=(
                "Dados do laudo: {payload}\n\n"
                "Produza a seção narrativa em 3 parágrafos."
            ),
            system=SYSTEM,
            max_tokens=1500,
        )

        data, ok = self.parse_json_response(
            resp,
            fallback={
                "narrativa": resp[:2000] if resp else "",
                "palavras_chave": [],
                "tom": "informativo",
            },
            campos_esperados=("narrativa",),
        )

        narrativa = (data.get("narrativa") or "").strip()
        if not narrativa:
            return AgentResult(
                agent_id=self.agent_id,
                status="ERRO",
                output={"erro": "narrativa vazia", "raw": resp[:300]},
                confidence=0.0,
            )

        confidence = self.derivar_confidence(ok, data, campos_esperados=("narrativa", "tom"))
        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output={
                "narrativa": narrativa,
                "palavras_chave": data.get("palavras_chave") or [],
                "tom": data.get("tom", "informativo"),
                "tamanho_chars": len(narrativa),
            },
            confidence=confidence,
        )
