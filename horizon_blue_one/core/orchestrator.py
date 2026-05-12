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

from horizon_blue_one.agents.base_agent import AgentResult, BaseAgent
from horizon_blue_one.core.ledger import async_log_event
from horizon_blue_one.core.limiares import (
    PF_GATE_AMPLO,
    PF_GATE_ARQUIVA,
    PF_GATE_REDUZIDO,
)
from horizon_blue_one.core.precalc import precalcular

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
    # ─── 7 agentes consolidados (default a partir de 2026-05-08) ──────────────
    "S1": "s1_sentinel",   "S2": "s2_forense",   "S3": "s3_fiscal",
    "S4": "s4_contabil",   "S5": "s5_nfa",       "S6": "s6_rh",
    "S7": "s7_ceo",
    # ─── Alias compat: A-00 (CEO) → S7 ────────────────────────────────────────
    "A-00": "s7_ceo",
    # ─── Legacy (preservado em _legacy/ para rollback e regressão) ────────────
    "A-01_LEGACY": "_legacy.a01_junior",   "A-02_LEGACY": "_legacy.a02_protetor",
    "A-03_LEGACY": "_legacy.a03_zerotrust", "A-04_LEGACY": "_legacy.a04_vigilante",
    "A-05_LEGACY": "_legacy.a05_engenheiro_erp", "A-06_LEGACY": "_legacy.a06_extrator",
    "A-07_LEGACY": "_legacy.a07_auditoria_assurance", "A-08_LEGACY": "_legacy.a08_auditor_nfa",
    "A-09_LEGACY": "_legacy.a09_auditor_ti", "A-10_LEGACY": "_legacy.a10_auditor_patrimonio",
    "A-11_LEGACY": "_legacy.a11_planejador_tributario", "A-12_LEGACY": "_legacy.a12_descobridor_deducoes",
    "A-13_LEGACY": "_legacy.a13_monitor_conformidade", "A-14_LEGACY": "_legacy.a14_avaliador_risco",
    "A-15_LEGACY": "_legacy.a15_juridico_ext", "A-16_LEGACY": "_legacy.a16_lgpd",
    "A-17_LEGACY": "_legacy.a17_previsor_caixa", "A-18_LEGACY": "_legacy.a18_analista_csuite",
    "A-19_LEGACY": "_legacy.a19_contabilista_ia", "A-20_LEGACY": "_legacy.a20_esocial_ia",
    "A-21_LEGACY": "_legacy.a21_auditor_icms", "A-22_LEGACY": "_legacy.a22_auditor_itr",
    "A-23_LEGACY": "_legacy.a23_analista_anomalias", "A-24_LEGACY": "_legacy.a24_classificador_cfop",
    "A-25_LEGACY": "_legacy.a25_auditor_lcdpr", "A-26_LEGACY": "_legacy.a26_auditor_biologicos",
    "A-27_LEGACY": "_legacy.a27_epsilon_forensic",
}

# Pipeline default consolidado: S1..S7 (CEO chamado por último automaticamente)
PIPELINE_DEFAULT = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]


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
        paralelo: bool = True,
        early_exit: bool = True,
        max_tokens_orcamento: int = 100_000,
    ) -> dict[str, AgentResult]:
        """Roda os agentes acumulando resultados.

        F7: paralelização via asyncio.gather (default).
        Early-exit: se score < 30 e zero anomalias, pula LLMs caros.
        Token budget: corta o pipeline se exceder `max_tokens_orcamento` tokens
                      (custo + latência sob controle em audits patológicos).
        Pré-cálculo determinístico (precalc) é injetado no payload uma única vez.
        """
        from horizon_blue_one.core.token_router import snapshot_stats
        snap_inicial = snapshot_stats()
        tokens_inicio = int(snap_inicial.get("total_tokens", 0))
        await self.bus.start()
        try:
            resultados: dict[str, AgentResult] = {}
            payload = {**payload, "resultados_agentes": {}}

            # ── Pré-cálculo determinístico (UMA vez) ─────────────────────────
            payload = await precalcular(payload)
            pre = payload.get("__precalc__", {})

            # ── Early exit: audit limpa não precisa de LLM ───────────────────
            if early_exit and self._audit_limpa(pre):
                logger.info("orchestrator.early_exit", score=pre.get("xgboost", {}).get("score", 0))
                resultados["__EARLY_EXIT__"] = AgentResult(
                    agent_id="__SYSTEM__",
                    status="APROVADO",
                    output={
                        "motivo": "Audit determinística limpa — sem LLM",
                        "precalc": pre,
                    },
                    confidence=0.95,
                )
                return resultados

            # ── pf-gate: arquiva sem LLM se prob. autuação muito baixa ───────
            pf = float(pre.get("xgboost", {}).get("probabilidade_autuacao", 0) or 0)
            if pf < PF_GATE_ARQUIVA:
                logger.info("orchestrator.pf_gate_arquiva", pf=pf, limite=PF_GATE_ARQUIVA)
                resultados["__PF_GATE__"] = AgentResult(
                    agent_id="__SYSTEM__",
                    status="APROVADO",
                    output={
                        "motivo": f"pf={pf:.0%} < {PF_GATE_ARQUIVA:.0%} — arquivado sem LLM",
                        "precalc": pre,
                    },
                    confidence=0.90,
                )
                return resultados

            # ── pf-gate: filtra agentes para pipelines reduzido/amplo ────────
            agentes, motivo_gate = self._aplicar_gate(list(agentes), pf)
            logger.info("orchestrator.pf_gate", pf=pf, motivo=motivo_gate, agentes=agentes)

            agentes_executar = [a for a in agentes if not (a in ("A-00", "S7") and chamar_ceo_no_fim)]
            payload["__orcamento_tokens__"] = max_tokens_orcamento
            payload["__tokens_inicio__"]    = tokens_inicio

            if paralelo:
                resultados = await self._executar_paralelo(agentes_executar, payload)
                # Atualiza payload acumulado para CEO
                for aid, r in resultados.items():
                    payload["resultados_agentes"][aid] = (
                        r.output if isinstance(r.output, dict) else {"raw": str(r.output)}
                    )
            else:
                resultados = await self._executar_sequencial(agentes_executar, payload)

            # CEO recebe TUDO agregado (S7 substitui A-00; alias preservado)
            ceo_id = "S7" if "S7" in agentes else ("A-00" if "A-00" in agentes else None)
            if chamar_ceo_no_fim and ceo_id:
                try:
                    ceo = _instanciar(ceo_id)
                    payload_ceo = {
                        **payload,
                        "score_origem": "orchestrator",
                        "score_risco": _score_consolidado(resultados, pre),
                    }
                    resultados[ceo_id] = await ceo.process(payload_ceo)
                    await self.bus.publish(EventoBus(
                        tipo="CONCLUIDO", agent_id=ceo_id,
                        payload={"total_agentes": len(resultados)},
                    ))
                except Exception as exc:
                    logger.error("orchestrator.ceo_erro", erro=str(exc))

            return resultados
        finally:
            await self.bus.stop()

    @staticmethod
    def _aplicar_gate(agentes: list[str], pf: float) -> tuple[list[str], str]:
        """Filtra pipeline pela probabilidade de autuação determinística (precalc).

        S7 (CEO) sempre permanece — é o consolidador final.
        Faixas (limiares.py):
          pf <  PF_GATE_REDUZIDO (0.65) → S3 + S5 + S7
          pf <  PF_GATE_AMPLO    (0.85) → S1 + S2 + S3 + S5 + S7 (sem S4/S6)
          pf >= PF_GATE_AMPLO          → mantém lista completa
        """
        if pf < PF_GATE_REDUZIDO:
            permitidos = {"S3", "S5", "S7", "A-00"}
            motivo = f"reduzido (pf={pf:.0%} < {PF_GATE_REDUZIDO:.0%}): S3+S5+S7"
        elif pf < PF_GATE_AMPLO:
            permitidos = {"S1", "S2", "S3", "S5", "S7", "A-00"}
            motivo = f"amplo (pf={pf:.0%} < {PF_GATE_AMPLO:.0%}): S1+S2+S3+S5+S7"
        else:
            return agentes, f"full (pf={pf:.0%} >= {PF_GATE_AMPLO:.0%}): pipeline completo"
        return [a for a in agentes if a in permitidos], motivo

    @staticmethod
    def _audit_limpa(pre: dict) -> bool:
        """Heurística early-exit: zero detecções, score baixo, sem divergência fiscal."""
        if not pre:
            return False
        det = pre.get("detectores", {})
        xgb = pre.get("xgboost", {})
        cfop = pre.get("cfop", {})
        lcdpr = pre.get("lcdpr", {})
        sem_deteccoes = (
            not det.get("carrossel")
            and not det.get("smurfing")
            and not det.get("devolucao_posterior")
            and not det.get("anomalia_temporal")
            and not (det.get("fornecedor_fantasma") or [])
        )
        score_ok = float(xgb.get("score", 0)) < 30
        cfop_ok  = int(cfop.get("total_divergencias", 0)) == 0
        lcdpr_ok = abs(float(lcdpr.get("divergencia", 0))) < 100
        return sem_deteccoes and score_ok and cfop_ok and lcdpr_ok

    async def _executar_um(self, aid: str, payload: dict) -> tuple[str, AgentResult | None]:
        t0 = time.time()
        try:
            ag = _instanciar(aid)
            result = await ag.process(payload)
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
            return aid, result
        except Exception as exc:
            logger.error("orchestrator.agente_erro", agent_id=aid, erro=str(exc))
            await self.bus.publish(EventoBus(
                tipo="ERRO", agent_id=aid, payload={"erro": str(exc)[:200]},
            ))
            return aid, None

    async def _executar_paralelo(self, agentes: list[str], payload: dict) -> dict[str, AgentResult]:
        """F7: roda agentes independentes em ondas, checando token budget entre ondas.

        Onda 1 (Haiku barato): S1, S3, S5, S6 — agentes determinísticos/fiscais
        Onda 2 (Sonnet/Opus caro): S2, S4    — forense e contábil

        Antes da Onda 2, verifica `__orcamento_tokens__`: se já excedeu,
        pula os caros (registra warning) e retorna o que tem.
        """
        from horizon_blue_one.core.token_router import snapshot_stats

        ONDA_BARATA = {"S1", "S3", "S5", "S6"}
        baratos = [a for a in agentes if a in ONDA_BARATA]
        caros = [a for a in agentes if a not in ONDA_BARATA]

        resultados: dict[str, AgentResult] = {}

        # Onda 1
        if baratos:
            outs = await asyncio.gather(*[self._executar_um(a, payload) for a in baratos])
            resultados.update({aid: r for aid, r in outs if r is not None})

        # Check budget entre ondas
        orcamento = int(payload.get("__orcamento_tokens__", 0))
        tokens_inicio = int(payload.get("__tokens_inicio__", 0))
        if orcamento > 0 and caros:
            consumido = int(snapshot_stats().get("total_tokens", 0)) - tokens_inicio
            if consumido > orcamento:
                logger.warning(
                    "orchestrator.budget_exceeded_paralelo",
                    consumido=consumido,
                    orcamento=orcamento,
                    pulados=caros,
                )
                return resultados

        # Onda 2
        if caros:
            outs = await asyncio.gather(*[self._executar_um(a, payload) for a in caros])
            resultados.update({aid: r for aid, r in outs if r is not None})

        return resultados

    async def _executar_sequencial(self, agentes: list[str], payload: dict) -> dict[str, AgentResult]:
        """Modo legado: cada agente vê resultados dos anteriores."""
        from horizon_blue_one.core.token_router import snapshot_stats
        resultados: dict[str, AgentResult] = {}
        orcamento = int(payload.get("__orcamento_tokens__", 0))
        tokens_inicio = int(payload.get("__tokens_inicio__", 0))
        for aid in agentes:
            if orcamento > 0:
                consumido = int(snapshot_stats().get("total_tokens", 0)) - tokens_inicio
                if consumido > orcamento:
                    logger.warning("orchestrator.budget_exceeded", consumido=consumido,
                                   orcamento=orcamento, restantes=len(agentes) - len(resultados))
                    break
            _, r = await self._executar_um(aid, payload)
            if r is not None:
                resultados[aid] = r
                payload["resultados_agentes"][aid] = (
                    r.output if isinstance(r.output, dict) else {"raw": str(r.output)}
                )
        return resultados


def _score_consolidado(resultados: dict[str, AgentResult], pre: dict | None = None) -> float:
    """F10: lê score_risco/score/score_global E precalc.xgboost.score."""
    scores: list[float] = []
    # 1) Score do precalc (fonte canônica determinística)
    if pre:
        s = pre.get("xgboost", {}).get("score", 0) or pre.get("xgboost", {}).get("score_risco", 0)
        try: scores.append(float(s))
        except (TypeError, ValueError): pass
    # 2) Scores reportados pelos agentes (A-07/A-23 legacy + S2 forense)
    for aid in ("A-07", "A-23", "S2", "S7"):
        r = resultados.get(aid)
        if r and isinstance(r.output, dict):
            for chave in ("score_risco", "score", "score_global"):
                if chave in r.output:
                    try:
                        scores.append(float(r.output[chave]))
                        break
                    except (TypeError, ValueError):
                        continue
    return max(scores) if scores else 0.0
