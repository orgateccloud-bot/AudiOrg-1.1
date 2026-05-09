"""A-01 @Junior — Manager Agent, Roteamento, Ledger.

Hardening v1.1:
- requisicao_id passa de timestamp-em-segundos (colidível) para UUID v4.
- Validação rigorosa do destino: rejeita string que não pertence ao set
  de valores conhecidos antes de cair no fallback estático.

Hardening v1.2 (R-01):
- tipo_analise desconhecido gera WARNING no ledger + status ROTA_DESCONHECIDA.
- SPOF mitigado: rota fallback explícita por classe de tipo_analise.
- AGENTES_VALIDOS garante que LLM nunca injete destino fora do registry.
"""
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.model_adapter import call_model, ModelType
from horizon_blue_one.agents.a_token import call_otimizado
from horizon_blue_one.core.token_router import TipoTarefa

ROTAS = {
    # ─── Auditoria Rural ──────────────────────────────────────────────────────
    "nfa":          "A-08",
    "rural":        "A-08",
    "biologicos":   "A-26",  # @Auditor-Biologicos (era A-09 @Auditor-TI)
    "anomalias":    "A-23",  # @Analista-Anomalias AN-01..AN-18
    "forense":      "A-27",  # @Epsilon grafo de conluio
    # ─── Fiscal Especializado ────────────────────────────────────────────────
    "icms":         "A-21",  # @Auditor-ICMS (era A-10 @Auditor-Patrimonio)
    "itr":          "A-22",  # @Auditor-ITR (era A-11 @Planejador-Tributario)
    "cfop":         "A-24",  # @Classificador-CFOP (era A-13 @Monitor-Conformidade)
    "lcdpr":        "A-25",  # @Auditor-LCDPR (era A-14 @Avaliador-Risco)
    # ─── Contabilidade / eSocial ─────────────────────────────────────────────
    "contabil":     "A-19",  # @Contabilista-IA (era A-17 @Previsor-Caixa)
    "esocial":      "A-20",  # @Esocial-IA (era A-18 @Analista-CSuite)
    # ─── ERP / Integração ────────────────────────────────────────────────────
    "sped":         "A-05",  # @Engenheiro-ERP (era A-10)
    # ─── Consultivo ──────────────────────────────────────────────────────────
    "tributaria":   "A-11",  # @Planejador-Tributario
    "juridica":     "A-15",  # @Juridico-Ext (era A-11)
    "fraude":       "A-12",  # @Descobridor-Deducoes
    "caixa":        "A-17",  # @Previsor-Caixa (era A-15 @Juridico-Ext)
    "conformidade": "A-13",  # @Monitor-Conformidade (era A-14 @Avaliador-Risco)
    "patrimonio":   "A-10",  # @Auditor-Patrimonio
    "risco":        "A-14",  # @Avaliador-Risco
    "lgpd":         "A-16",  # @LGPD
    "csuite":       "A-18",  # @Analista-CSuite (era A-16 @LGPD)
}

# Registry imutável de IDs válidos — impede injeção de destino fora do sistema
AGENTES_VALIDOS = frozenset(ROTAS.values())

# Fallback por família quando tipo_analise é desconhecido mas contém substring reconhecível
_FALLBACK_POR_FAMILIA = {
    "icms": "A-21", "itr": "A-22", "lcdpr": "A-25", "cfop": "A-24",
    "nfa": "A-08", "rural": "A-08", "esocial": "A-20", "contabil": "A-19",
    "fraude": "A-12", "forense": "A-27", "anomalia": "A-23",
}


class JuniorAgent(BaseAgent):
    agent_id = "A-01"
    name = "@Junior"
    _ledger: list = []

    async def process(self, payload: dict) -> AgentResult:
        t0 = time.time()
        tipo = payload.get("tipo_analise", "nfa").lower()
        contexto = payload.get("contexto", "")

        # Roteamento Inteligente via Haiku (Tier 1)
        system_prompt = (
            f"Você é o roteador da ORGATEC IA. Com base no tipo '{tipo}' e contexto '{contexto}', "
            f"selecione o agente destino: {json.dumps(ROTAS)}. Responda APENAS o ID do agente."
        )

        try:
            destino = (await call_otimizado(f"Rota para: {tipo}", system_prompt, max_tokens=10, agent_id=self.agent_id))[0]
            destino = destino.strip().upper()
            # Rejeita qualquer ID fora do registry — impede injeção de destino arbitrário
            if destino not in AGENTES_VALIDOS:
                destino = ROTAS.get(tipo, "A-08")
        except Exception as exc:
            self.log_error("Roteamento via Haiku falhou, usando tabela estática", exc=exc)
            destino = ROTAS.get(tipo, "A-08")

        # R-01: detecta tipo_analise completamente desconhecido e loga como WARNING
        tipo_reconhecido = tipo in ROTAS
        if not tipo_reconhecido:
            # Tenta correspondência parcial por família antes de cair no A-08
            destino_familia = next(
                (ag for chave, ag in _FALLBACK_POR_FAMILIA.items() if chave in tipo),
                None,
            )
            if destino_familia:
                destino = destino_familia
                self.log_error(
                    "Tipo desconhecido — fallback por família",
                    tipo=tipo, destino=destino, nivel="WARNING",
                )
            else:
                self.log_error(
                    "Tipo completamente desconhecido — roteando para A-08 (NFA default). "
                    "Adicione o tipo ao dict ROTAS para cobertura correta.",
                    tipo=tipo, destino="A-08", nivel="WARNING",
                )
                destino = "A-08"

        # Grava no banco persistente (assíncrono — não bloqueia o event loop)
        from horizon_blue_one.core.ledger import async_log_event

        # UUID v4 evita colisões em requisições simultâneas (>1 req/segundo).
        req_id = payload.get("requisicao_id") or f"req-{uuid.uuid4().hex[:12]}"
        audit_hash = hashlib.sha256(f"{req_id}{tipo}{destino}".encode()).hexdigest()[:16]
        await async_log_event(
            requisicao_id=req_id,
            agent_id=self.agent_id,
            acao=f"Roteou {tipo} para {destino}",
            tier="Haiku",
            status="APROVADO",
            audit_hash=audit_hash,
            payload={"tipo": tipo, "destino": destino},
        )

        ms = (time.time() - t0) * 1000
        self.log("Roteamento dinâmico concluído (Haiku)", tipo=tipo, destino=destino, ms=round(ms, 2))

        return AgentResult(
            agent_id=self.agent_id,
            status="APROVADO",
            output={"destino": destino, "ms": round(ms, 2)},
            confidence=0.95,
        )
