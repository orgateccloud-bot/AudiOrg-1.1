"""Classe base para todos os agentes ORGATEC IA — Pydantic V2 + audit_hash SHA-256.

Inclui `_call_llm()` que aplica @Delta (privacy.anonymize_payload) automaticamente
antes de chamar o modelo. Agentes não devem chamar model_adapter.call_model()
direto — sempre passar pelo BaseAgent para garantir conformidade LGPD.
"""
import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Union

import structlog
from pydantic import BaseModel

from horizon_blue_one.core.model_adapter import ModelType, call_model
from horizon_blue_one.core.privacy import anonymize_payload

logger = structlog.get_logger()


class AgentResult(BaseModel):
    agent_id: str
    status: str          # APROVADO | REJEITADO | ESCALADO | ERRO
    output: Union[dict, Any]
    confidence: float    # 0.0 – 1.0
    timestamp: str = ""
    audit_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

        raw = (
            self.output.model_dump_json()
            if isinstance(self.output, BaseModel)
            else json.dumps(self.output, sort_keys=True, ensure_ascii=False, default=str)
        )
        try:
            from horizon_blue_one.core.config import settings
            hash_len = settings.AUDIT_HASH_LEN
        except Exception:
            hash_len = 64
        self.audit_hash = hashlib.sha256(raw.encode()).hexdigest()[:hash_len]


class BaseAgent(ABC):
    agent_id: str
    name: str

    @abstractmethod
    async def process(self, payload: dict) -> AgentResult: ...

    # ── Logging ──────────────────────────────────────────────────────────────

    def log(self, msg: str, **kwargs):
        structlog.get_logger().info(msg, agent_id=self.agent_id, agent_name=self.name, **kwargs)

    def log_error(self, msg: str, exc: Exception | None = None, **kwargs):
        structlog.get_logger().error(
            msg,
            agent_id=self.agent_id,
            agent_name=self.name,
            error=str(exc) if exc else None,
            **kwargs,
        )

    # ── Chamada protegida ao LLM ─────────────────────────────────────────────

    async def _call_llm(
        self,
        model_type: ModelType,
        prompt_payload: dict,
        prompt_template: str,
        system: str = "",
        max_tokens: int = 4096,
        requisicao_id: str | None = None,
    ) -> str:
        """Aplica @Delta no payload e chama o modelo.

        Args:
            model_type: HAIKU | SONNET | OPUS
            prompt_payload: dict que será inserido no prompt — passa por @Delta
            prompt_template: string com `{payload}` placeholder
            system: system prompt (não anonimizado — é texto técnico)
            max_tokens: limite de saída
            requisicao_id: UUID rastreável (default: gerado aqui)

        Returns:
            Resposta bruta do modelo (string).
        """
        req_id = requisicao_id or str(uuid.uuid4())
        payload_seguro = anonymize_payload(
            prompt_payload, requisicao_id=req_id, agente=self.agent_id,
        )
        prompt = prompt_template.format(payload=json.dumps(payload_seguro, ensure_ascii=False, default=str))
        return await call_model(model_type, prompt, system, max_tokens=max_tokens)

    # ── Helpers de parsing ───────────────────────────────────────────────────

    @staticmethod
    def parse_json_response(
        resp: str,
        fallback: dict,
        campos_esperados: tuple[str, ...] = (),
    ) -> tuple[dict, bool]:
        try:
            data = json.loads(resp)
            if not isinstance(data, dict):
                return fallback, False
            if campos_esperados and not all(k in data for k in campos_esperados):
                return {**fallback, **data}, False
            return data, True
        except (json.JSONDecodeError, TypeError, ValueError):
            return fallback, False

    @staticmethod
    def derivar_confidence(
        parseou_ok: bool,
        data: dict,
        campos_esperados: tuple[str, ...] = (),
        confidence_base: float = 0.85,
    ) -> float:
        if not isinstance(data, dict):
            return 0.50
        if campos_esperados:
            presentes = sum(1 for k in campos_esperados if k in data and bool(data[k]))
            cobertura = presentes / len(campos_esperados)
        else:
            cobertura = 1.0
        if not parseou_ok:
            return round(0.50 * cobertura, 4)
        declarada = data.get("confianca")
        if isinstance(declarada, (int, float)) and 0.0 <= declarada <= 1.0:
            return float(declarada)
        return round(confidence_base * cobertura, 4)
