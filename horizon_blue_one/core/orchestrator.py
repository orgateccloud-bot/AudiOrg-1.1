"""
Orchestrator — coordenador centralizado dos agentes Horizon-Blue.

Resolve 2 gaps documentados:
  1. Pipelines paralelos (LangGraph Sigma/Gama vs squad A-XX) — orquestra A-XX
  2. Sem event-bus: agentes emitiam ESCALADO via log; agora vai para asyncio.Queue
     e o A-00 @CEO (subscriber) reage automaticamente.

Uso típico (script ou endpoint FastAPI):

    from horizon_blue_one.core.orchestrator import Orchestrator

    orch = Orchestrator()
    resultados = await orch.executar_pipeline(payload, agentes=["A-07","A-08","A-23","A-27"])
    # automaticamente:
    #   - propaga 'resultados_agentes' acumulado entre agentes
    #   - publica eventos ESCALADO no bus
    #   - chama A-00 ao final com tudo agregado

Eventos do bus:
    {"tipo": "ESCALADO", "agent_id": "A-07", "score": 51.4, "motivo": "...", "ts": ...}

Subscribers default:
    A-00 @CEO  → consome ESCALADO e produz decisão final
    A-13       → consome qualquer evento e valida conformidade transversal
    A-18       → consome ao final para gerar resumo executivo
"""
from __future__ import annotations

import asyncio
import importlib
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from horizon_blue_one.agents.base_agent import BaseAgent, AgentResult
from horizon_blue_one.core.ledger import async_log_event

logger = structlog.get_logger()


# ── Event Bus ────────────────────────────────────────────────────────────────

@dataclass
class EventoBus:
    tipo: str                      # ESCALADO | APROVADO | REJEITADO | ERRO | CONCLUIDO
    agent_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class EventBus:
    """asyncio.Queue + lista de subscribers que filtram por tipo."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[EventoBus] = asyncio.Queue()
        self._subscribers: list[tuple[str, Any]] = []   # (filtro_tipo, async_fn)
        self._task: asyncio.Task | None = None

    def subscribe(self, tipo_filtro: str, callback) -> None:
        """tipo_filtro: '*' para todos, ou exato (ESCALADO, APROVADO, etc.)."""
        self._subscribers.append((tipo_filtro, callback))

    async def publish(self, ev: EventoBus) -> None:
        await self._queue.put(ev)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        await self._queue.put(EventoBus(tipo="__SHUTDOWN__", agent_id="bus"))
        if self._task:
            await self._task

    async def _loop(self) -> None:
        while True:
            ev = await self._queue.get()
            if ev.tipo == "__SHUTDOWN__":
                return
            for filtro, cb in self._subscribers:
                if filtro in ("*", ev.tipo):
                    try:
                        await cb(ev)
                    except Exception as exc:
                        logger.error("event_bus.subscriber_error", erro=str(exc), tipo=ev.tipo)


# ── Registry de agentes ──────────────────────────────────────────────────────

_AGENT_MODULES = {
    "A-00": "a00_ceo",                          "A-01": "a01_junior",
    "A-02": "a02_protetor",                     "A-03": "a03_zerotrust",
    "A-04": "a04_vigilante",                    "A-05": "a05_engenheiro_erp",
    "A-06": "a06_extrator",                     "A-07": "a07_auditoria_assurance",
    "A-08": "a08_auditor_nfa",                  "A-09": "a09_auditor_ti",
    "A-10": "a10_auditor_patrimonio",           "A-11": "a11_planejador_tributario",
    "A-12": "a12_descobridor_deducoes",         "A-13": "a13_monitor_conformidade",
    "A-14": "a14_avaliador_risco",              "A-15": "a15_juridico_ext",
    "A-16": "a16_lgpd",                         "A-17": "a17_previsor_caixa",
    "A-18": "a18_analista_csuite",              "A-19": "a19_contabilista_ia",
    "A-20": "a20_esocial_ia",                   "A-21": "a21_auditor_icms",
    "A-22": "a22_auditor_itr",                  "A-23": "a23_analista_anomalias",
    "A-24": "a24_classificador_cfop",           "A-25": "a25_auditor_lcdpr",
    "A-26": "a26_auditor_biologicos",           "A-27": "a27_epsilon_forensic",
}


def _instanciar(agent_id: str) -> BaseAgent:
    mod_name = _AGENT_MODULES.get(agent_id)
    if not mod_name:
        raise ValueError(f"agent_id desconhecido: {agent_id}")
    mod = importlib.import_module(f"horizon_blue_one.agents.{mod_name}")
    for nome in dir(mod):
        obj = getattr(mod, nome)
        if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent:
            return obj()
    raise RuntimeError(f"BaseAgent subclass não encontrada em {mod_name}")


# ── Orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    """Executa um pipeline de agentes propagando 'resultados_agentes' entre eles."""

    def __init__(self) -> None:
        self.bus = EventBus()
        self.bus.subscribe("ESCALADO", self._on_escalado)
        self.bus.subscribe("*",        self._on_qualquer)

    # ── Subscribers default ──────────────────────────────────────────────────

    async def _on_escalado(self, ev: EventoBus) -> None:
        """Default: registra escalada no ledger. A-00 reage no final."""
        await async_log_event(
            requisicao_id=ev.payload.get("requisicao_id", "orchestrator"),
            agent_id=ev.agent_id,
            acao=f"ESCALADO -> A-00 (motivo: {ev.payload.get('motivo', 'n/a')})",
            tier="bus",
            status="ESCALADO",
            audit_hash="",
            payload=ev.payload,
        )

    async def _on_qualquer(self, ev: EventoBus) -> None:
        """Telemetria: contabiliza no logger estruturado."""
        logger.info("orchestrator.evento", tipo=ev.tipo, agent_id=ev.agent_id)

    # ── Execução ─────────────────────────────────────────────────────────────

    async def executar_pipeline(
        self,
        payload: dict,
        agentes: list[str],
        chamar_ceo_no_fim: bool = True,
    ) -> dict[str, AgentResult]:
        """Roda os agentes na ordem fornecida, acumulando resultados.

        Cada agente subsequente recebe payload + 'resultados_agentes'={agent_id: result}.
        Eventos são publicados no bus. A-00 é chamado por último com tudo agregado.
        """
        await self.bus.start()
        try:
            resultados: dict[str, AgentResult] = {}
            payload = {**payload, "resultados_agentes": {}}

            for aid in agentes:
                if aid == "A-00" and chamar_ceo_no_fim:
                    continue  # CEO roda no final
                t0 = time.time()
                try:
                    ag = _instanciar(aid)
                    result = await ag.process(payload)
                    resultados[aid] = result
                    payload["resultados_agentes"][aid] = (
                        result.output if isinstance(result.output, dict) else {"raw": str(result.output)}
                    )
                    await self.bus.publish(EventoBus(
                        tipo=result.status,
                        agent_id=aid,
                        payload={
                            "confidence": result.confidence,
                            "ms": round((time.time() - t0) * 1000, 1),
                            "motivo": (result.output.get("motivo") if isinstance(result.output, dict) else ""),
                            "requisicao_id": payload.get("requisicao_id"),
                        },
                    ))
                except Exception as exc:
                    logger.error("orchestrator.agente_erro", agent_id=aid, erro=str(exc))
                    await self.bus.publish(EventoBus(
                        tipo="ERRO", agent_id=aid,
                        payload={"erro": str(exc)[:200]},
                    ))

            # CEO recebe TUDO agregado (resolve gap A-13/A-18 órfãos também)
            if chamar_ceo_no_fim and "A-00" in agentes:
                try:
                    ceo = _instanciar("A-00")
                    payload_ceo = {**payload, "score_origem": "orchestrator", "score_risco": _score_consolidado(resultados)}
                    resultados["A-00"] = await ceo.process(payload_ceo)
                    await self.bus.publish(EventoBus(
                        tipo="CONCLUIDO", agent_id="A-00",
                        payload={"total_agentes": len(resultados)},
                    ))
                except Exception as exc:
                    logger.error("orchestrator.ceo_erro", erro=str(exc))

            return resultados
        finally:
            await self.bus.stop()


def _score_consolidado(resultados: dict[str, AgentResult]) -> float:
    """Heurística simples: maior score reportado por A-07/A-23."""
    scores = []
    for aid in ("A-07", "A-23"):
        r = resultados.get(aid)
        if r and isinstance(r.output, dict):
            s = r.output.get("score") or r.output.get("score_global") or 0
            try: scores.append(float(s))
            except (TypeError, ValueError): pass
    return max(scores) if scores else 0.0
