"""A-Resolver — Resolução de ambiguidade na classificação de NFA-e.

A Regra-Mãe Python resolve ~85% dos casos com lógica determinística.
Os 15% restantes (remessa-leilão sem arremate registrado, transferência
intrafamiliar suspeita, notas sem destinatário claro) caem aqui.

Claude propõe a classificação com justificativa e grau de confiança.
A decisão final pertence ao contador — Claude apenas sugere.
"""
from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType

CLASSIFICACOES_VALIDAS = frozenset({
    "RECEITA", "DESPESA", "TRANSITO", "TRANSFERENCIA", "INCONCLUSIVO",
})

SYSTEM = """Você é o @Resolver — especialista em casos ambíguos de classificação NFA-e.

Aplica a Regra-Mãe (ótica do contribuinte):
- REMETENTE + VENDA               → RECEITA
- REMETENTE + REMESSA              → TRANSITO
- REMETENTE = DESTINATÁRIO         → TRANSFERENCIA (intra-CPF/CNPJ)
- DESTINATÁRIO                     → DESPESA

Casos ambíguos típicos:
- Remessa com posterior venda sem NF-e modelo 55 → consultar histórico
- Leilão sem arremate registrado → tratar como TRANSITO + alertar AN-08
- Transferência intrafamiliar mesmo grau (cônjuge, pais, filhos) → suspeita

Responda APENAS com JSON:
{
  "classificacao": "RECEITA|DESPESA|TRANSITO|TRANSFERENCIA|INCONCLUSIVO",
  "justificativa": "...",
  "anomalia_sugerida": "AN-XX|null",
  "confianca": 0.0-1.0
}
"""


class AResolverAgent(BaseAgent):
    agent_id = "A-RESOLVER"
    name = "@Resolver"

    async def process(self, payload: dict) -> AgentResult:
        """Espera payload: {nota: dict, cpf_contribuinte: str, historico: list}."""
        nota = payload.get("nota") or {}
        cpf_contrib = payload.get("cpf_contribuinte") or ""
        historico = payload.get("historico") or []

        if not nota:
            return AgentResult(
                agent_id=self.agent_id,
                status="REJEITADO",
                output={"erro": "nota vazia"},
                confidence=0.0,
            )

        self.log(
            "Resolvendo ambiguidade",
            numero=nota.get("numero"),
            natureza=nota.get("natureza"),
            valor=nota.get("valor_total"),
            qtd_historico=len(historico),
        )

        resp = await self._call_llm(
            model_type=ModelType.SONNET,
            prompt_payload={
                "nota": nota,
                "cpf_contribuinte": cpf_contrib,
                "historico_resumido": historico[-10:],
            },
            prompt_template=(
                "Caso ambíguo:\n{payload}\n\n"
                "Aplique a Regra-Mãe e proponha classificação."
            ),
            system=SYSTEM,
            max_tokens=800,
        )

        data, ok = self.parse_json_response(
            resp,
            fallback={
                "classificacao": "INCONCLUSIVO",
                "justificativa": "Parser do modelo falhou",
                "anomalia_sugerida": None,
                "confianca": 0.0,
            },
            campos_esperados=("classificacao", "justificativa"),
        )

        # Whitelist: rejeita classes inventadas pelo modelo
        classe = data.get("classificacao", "INCONCLUSIVO")
        if classe not in CLASSIFICACOES_VALIDAS:
            self.log_error(f"Classificação fora do whitelist: {classe}")
            classe = "INCONCLUSIVO"
            data["classificacao"] = classe
            data["confianca"] = 0.0

        confidence = self.derivar_confidence(
            ok, data,
            campos_esperados=("classificacao", "justificativa", "confianca"),
        )

        status = "APROVADO" if classe != "INCONCLUSIVO" and confidence >= 0.6 else "ESCALADO"

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output=data,
            confidence=confidence,
        )
