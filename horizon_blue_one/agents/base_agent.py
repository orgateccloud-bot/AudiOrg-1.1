"""Classe base para todos os agentes ORGATEC IA — Pydantic V2 + audit_hash SHA-256."""
import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Union

import structlog
from pydantic import BaseModel

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
            else json.dumps(self.output, sort_keys=True, ensure_ascii=False)
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
    async def call_com_retry(
        prompt: str,
        system: str,
        campos_esperados: tuple[str, ...],
        agent_id: str,
        max_tokens: int = 1024,
        max_tentativas: int = 2,
        **kwargs,
    ) -> tuple[dict, bool, str]:
        """F20: chama LLM com retry curto se JSON sair malformado ou faltar campos.

        Retorna (data_parseado, parseou_ok, resposta_bruta_final).
        Não levanta — devolve fallback {} em último caso para o agente decidir.
        """
        from horizon_blue_one.agents.a_token import call_otimizado

        ultima_resp = ""
        tentativa_prompt = prompt
        for tentativa in range(max_tentativas):
            ultima_resp, _ = await call_otimizado(
                tentativa_prompt, system,
                agent_id=agent_id,
                max_tokens=max_tokens,
                **kwargs,
            )
            try:
                data = json.loads(ultima_resp)
            except (json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, dict) and all(k in data for k in campos_esperados):
                return data, True, ultima_resp
            faltantes = [k for k in campos_esperados if not isinstance(data, dict) or k not in data]
            tentativa_prompt = (
                f"{prompt}\n\nResposta anterior inválida (JSON malformado ou faltando "
                f"campos: {faltantes}). Retorne APENAS o JSON solicitado, sem texto."
            )
        return ({} if not isinstance(data, dict) else data), False, ultima_resp

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
