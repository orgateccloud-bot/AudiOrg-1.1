"""A-06 @Extrator-Faturas — OCR + XML Parsing via Claude Haiku.

Hardening v1.1:
- defusedxml em vez de xml.etree (proteção contra XXE/Billion-Laughs).
- except específico em vez de bare except (preserva KeyboardInterrupt/SystemExit).
"""
import json
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType


class ExtratorFaturasAgent(BaseAgent):
    agent_id = "A-06"
    name = "@Extrator-Faturas"

    async def process(self, payload: dict) -> AgentResult:
        texto = payload.get("texto_nfa", "")
        formato = payload.get("formato", "texto")

        self.log(f"Processando documento (Formato: {formato})", chars=len(texto))

        if formato == "xml" or texto.strip().startswith("<?xml"):
            # defusedxml: bloqueia DTDs externos e expansão de entidades por padrão.
            from defusedxml import ElementTree as ET
            try:
                root = ET.fromstring(texto)
                data = {
                    "numero": root.findtext(".//nNF"),
                    "data": root.findtext(".//dhEmi"),
                    "valor_total": root.findtext(".//vNF"),
                    "remetente_nome": root.findtext(".//emit/xNome"),
                    "destinatario_nome": root.findtext(".//dest/xNome"),
                    "status_extracao": "XML_PARSED_OK",
                }
            except Exception as e:
                self.log_error("Erro no parsing XML", exc=e)
                data = {"error": "Falha no XML", "raw": texto[:100]}
        else:
            # Fallback para LLM se for texto puro/OCR
            prompt = f"Extraia os campos da NFA-e/NF-e abaixo e retorne JSON: {texto}"
            resultado = await call_model(ModelType.HAIKU, prompt)
            try:
                data = json.loads(resultado)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                # Falha de parse: preservamos o conteúdo bruto para auditoria,
                # mas NÃO engolimos KeyboardInterrupt/SystemExit (era bare except antes).
                self.log_error("Falha ao decodificar JSON do extrator", exc=exc)
                data = {"raw": resultado}

        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output=data,
            confidence=0.98 if "status_extracao" in data else 0.85,
        )
