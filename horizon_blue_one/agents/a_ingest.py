"""A-Ingest — Ingestão semântica de PDF GIEF/SEFAZ-GO.

Lê o texto extraído por pdfplumber/PyMuPDF e devolve uma lista de notas
estruturadas compatível com o schema NotaInput. Claude faz APENAS a
extração textual — a validação numérica (soma de valores bate com total
do PDF?) é feita por Python depois.
"""
import json
from typing import Any

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.model_adapter import ModelType

SYSTEM = """Você é o agente de ingestão NFA-e do OrgAudi.
Recebe texto bruto extraído de um PDF GIEF/SEFAZ-GO e devolve JSON com
a lista de notas fiscais avulsas presentes.

Schema obrigatório para cada nota:
{
  "numero": str, "data": "YYYY-MM-DD", "natureza": "VENDA|COMPRA|REMESSA|TRANSITO|DEVOLUCAO",
  "valor_total": float, "remetente_cpf": str, "remetente_nome": str,
  "destinatario_cpf": str, "destinatario_nome": str, "cfop": str,
  "cabecas": int, "municipio": str, "posicao": "REMETENTE|DESTINATARIO"
}

Regras:
- Use 0 ou "" quando o campo não estiver no texto. NUNCA invente valor.
- "natureza" deve ser sempre uma das opções listadas; em caso de dúvida, "VENDA".
- Devolva apenas JSON válido: {"notas": [...], "total_extraido": float, "alertas": [...]}.
- "alertas" lista notas com campos faltando ou ilegíveis.
"""


class AIngestAgent(BaseAgent):
    agent_id = "A-INGEST"
    name = "@Ingest"

    async def process(self, payload: dict) -> AgentResult:
        """Espera payload: {pdf_texto: str, total_esperado: float|None}."""
        texto = (payload.get("pdf_texto") or "").strip()
        if not texto:
            return AgentResult(
                agent_id=self.agent_id,
                status="REJEITADO",
                output={"erro": "pdf_texto vazio"},
                confidence=0.0,
            )

        total_esperado = payload.get("total_esperado")
        self.log("Ingestão GIEF iniciada", chars=len(texto), total_esperado=total_esperado)

        # Sonnet é melhor que Haiku para extração estruturada de PDFs longos
        resp = await self._call_llm(
            model_type=ModelType.SONNET,
            prompt_payload={"texto": texto},
            prompt_template=(
                "Texto bruto do PDF GIEF:\n{payload}\n\n"
                "Extraia todas as notas fiscais avulsas seguindo o schema do system."
            ),
            system=SYSTEM,
            max_tokens=8000,
        )

        data, ok = self.parse_json_response(
            resp,
            fallback={"notas": [], "total_extraido": 0.0, "alertas": ["parser falhou"]},
            campos_esperados=("notas", "total_extraido"),
        )

        notas: list[dict[str, Any]] = data.get("notas") or []
        total_extraido = float(data.get("total_extraido") or 0.0)
        alertas: list[str] = list(data.get("alertas") or [])

        # Validação determinística: soma das notas bate com total_extraido?
        soma_real = round(sum(float(n.get("valor_total") or 0) for n in notas), 2)
        if abs(soma_real - total_extraido) > 0.5:
            alertas.append(
                f"Inconsistência: soma das notas ({soma_real}) ≠ total_extraido ({total_extraido})"
            )

        # Validação opcional contra total esperado (vindo do header do PDF)
        if total_esperado is not None:
            diff = abs(soma_real - float(total_esperado))
            if diff > 1.0:
                alertas.append(
                    f"Soma extraída ({soma_real}) diverge do total do PDF ({total_esperado})"
                )

        confidence = self.derivar_confidence(
            ok, data,
            campos_esperados=("notas", "total_extraido"),
            confidence_base=0.80,
        )
        # Penaliza confiança se há alertas de inconsistência
        if alertas:
            confidence = round(confidence * 0.7, 4)

        status = "ESCALADO" if alertas else "APROVADO"
        self.log(
            "Ingestão GIEF concluída",
            qtd_notas=len(notas),
            soma=soma_real,
            qtd_alertas=len(alertas),
            status=status,
        )

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            output={
                "notas": notas,
                "total_extraido": total_extraido,
                "soma_real": soma_real,
                "alertas": alertas,
            },
            confidence=confidence,
        )
