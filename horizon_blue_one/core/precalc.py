"""horizon_blue_one.core.precalc
Isolamento de __precalc__ entre requisicoes concorrentes (Issue #28).

SEGURANCA: Cada chamada a build_precalc retorna uma copia profunda do
payload via copy.deepcopy, garantindo que mutacoes internas nao vazem
entre corotinas concorrentes no FastAPI/asyncio.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
from contextvars import ContextVar
from decimal import Decimal
from typing import Any

logger = logging.getLogger("orgaudi.precalc")

_precalc_ctx: ContextVar[dict[str, Any] | None] = ContextVar(
    "_precalc_ctx", default=None
)

_CFOP_NATUREZA: dict[str, str] = {
    "5101": "VENDA", "5102": "VENDA", "5111": "VENDA", "5112": "VENDA",
    "5113": "VENDA", "5114": "VENDA", "5115": "VENDA", "5116": "VENDA",
    "5118": "VENDA", "5119": "VENDA", "5120": "VENDA", "5122": "VENDA",
    "5123": "VENDA", "5124": "VENDA", "5125": "VENDA",
    "5251": "REMESSA_CONSIGNACAO", "5252": "REMESSA_CONSIGNACAO",
    "5910": "REMESSA_LEILAO", "5911": "REMESSA_LEILAO", "5912": "REMESSA_LEILAO",
    "6101": "VENDA_INTERESTADUAL", "6102": "VENDA_INTERESTADUAL",
    "1101": "COMPRA", "1102": "COMPRA", "1111": "COMPRA", "1113": "COMPRA",
    "2101": "COMPRA_INTERESTADUAL", "2102": "COMPRA_INTERESTADUAL",
    "1201": "DEVOLUCAO", "1202": "DEVOLUCAO",
    "5201": "DEVOLUCAO", "5202": "DEVOLUCAO",
}

_CFOP_ICMS_REDUCAO: dict[str, Decimal] = {
    "5101": Decimal("0.12"), "5102": Decimal("0.12"),
    "6101": Decimal("0.12"), "6102": Decimal("0.12"),
    "5910": Decimal("0.00"), "5911": Decimal("0.00"), "5912": Decimal("0.00"),
    "1101": Decimal("0.00"), "1102": Decimal("0.00"),
}

_ITR_POR_MODULO: dict[str, Decimal] = {
    "0_50": Decimal("0.030"), "50_200": Decimal("0.020"),
    "200_500": Decimal("0.015"), "500_1000": Decimal("0.010"),
    "1000_5000": Decimal("0.008"), "acima_5000": Decimal("0.006"),
}


def _faixa_modulo(area_ha: float) -> str:
    if area_ha <= 50: return "0_50"
    if area_ha <= 200: return "50_200"
    if area_ha <= 500: return "200_500"
    if area_ha <= 1000: return "500_1000"
    if area_ha <= 5000: return "1000_5000"
    return "acima_5000"


def build_precalc(payload: dict[str, Any]) -> dict[str, Any]:
    """Constroi o dict __precalc__ com copia profunda do payload (Issue #28)."""
    safe_payload = copy.deepcopy(payload)
    notas: list[dict] = safe_payload.get("notas", [])
    area_ha: float = float(safe_payload.get("area_ha", 0.0))

    cfop_map: dict[str, str] = {}
    cfop_icms: dict[str, Decimal] = {}
    for nota in notas:
        cfop = str(nota.get("cfop", "")).strip()
        if cfop and cfop not in cfop_map:
            cfop_map[cfop] = _CFOP_NATUREZA.get(cfop, "DESCONHECIDO")
            cfop_icms[cfop] = _CFOP_ICMS_REDUCAO.get(cfop, Decimal("0.12"))

    faixa = _faixa_modulo(area_ha)
    aliquota_itr = _ITR_POR_MODULO.get(faixa, Decimal("0.030"))
    fingerprint = hashlib.sha256(
        json.dumps([n.get("numero", "") for n in notas], sort_keys=True).encode()
    ).hexdigest()[:16]

    safe_payload["__precalc__"] = {
        "cfop_natureza": cfop_map,
        "cfop_icms_aliquota": {k: str(v) for k, v in cfop_icms.items()},
        "area_ha": area_ha, "faixa_modulo": faixa,
        "aliquota_itr": str(aliquota_itr),
        "total_notas": len(notas), "fingerprint": fingerprint,
    }
    logger.debug("precalc_construido", fingerprint=fingerprint, total_notas=len(notas))
    return safe_payload


def set_precalc_ctx(precalc: dict[str, Any]) -> None:
    """Armazena o precalc no ContextVar da corotina atual."""
    _precalc_ctx.set(copy.deepcopy(precalc))


def get_precalc_ctx() -> dict[str, Any]:
    """Recupera o precalc do ContextVar da corotina atual (copia profunda)."""
    precalc = _precalc_ctx.get()
    if precalc is None:
        raise RuntimeError(
            "precalc nao inicializado. Chame set_precalc_ctx() antes."
        )
    return copy.deepcopy(precalc)


class PrecalcLock:
    """Lock asyncio por instancia para escrita segura em precalc."""
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
    async def __aenter__(self) -> "PrecalcLock":
        await self._lock.acquire()
        return self
    async def __aexit__(self, *args: Any) -> None:
        self._lock.release()


__all__ = ["build_precalc", "set_precalc_ctx", "get_precalc_ctx", "PrecalcLock"]
