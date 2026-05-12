"""Loader cacheado para data/funrural_aliquotas.yaml.

Centraliza leitura, validação Pydantic e fallback para constantes hard-coded
caso o YAML esteja ausente ou inválido. Mudanças nas alíquotas devem ocorrer
no YAML (com bump de versão), não aqui.
"""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class _Aliquotas(BaseModel):
    pj: float = Field(gt=0, lt=1)
    pf: float = Field(gt=0, lt=1)
    segurado_especial: float = Field(gt=0, lt=1)


class TabelaFUNRURAL(BaseModel):
    versao: str
    fonte: str
    corte_vigencia: date
    aliquotas_pre_corte: _Aliquotas
    aliquotas_pos_corte: _Aliquotas
    irpf_resultado_rural: float = Field(gt=0, lt=1)

    def aliquota(self, *, eh_pj: bool, eh_segurado_especial: bool, data_referencia: date) -> float:
        bloco = self.aliquotas_pos_corte if data_referencia >= self.corte_vigencia else self.aliquotas_pre_corte
        if eh_pj:
            return bloco.pj
        if eh_segurado_especial:
            return bloco.segurado_especial
        return bloco.pf


# Fallback usado se o YAML sumir ou ficar inválido em produção. Mantém vigentes
# os valores de 2026.1 — log de erro crítico avisa para arrumar o YAML.
_FALLBACK = TabelaFUNRURAL(
    versao="fallback-2026.1",
    fonte="hardcoded — usado só quando YAML falha",
    corte_vigencia=date(2026, 4, 1),
    aliquotas_pre_corte=_Aliquotas(pj=0.0205, pf=0.0150, segurado_especial=0.0150),
    aliquotas_pos_corte=_Aliquotas(pj=0.0223, pf=0.0163, segurado_especial=0.0150),
    irpf_resultado_rural=0.20,
)


def _path_yaml() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "funrural_aliquotas.yaml"


@lru_cache(maxsize=1)
def carregar_tabela() -> TabelaFUNRURAL:
    caminho = _path_yaml()
    try:
        with caminho.open(encoding="utf-8") as fp:
            dados = yaml.safe_load(fp)
        return TabelaFUNRURAL(**dados)
    except Exception as exc:  # noqa: BLE001 — fallback é a feature
        logger.critical(
            "FUNRURAL YAML falhou (%s) — usando fallback hard-coded versao=%s",
            exc,
            _FALLBACK.versao,
        )
        return _FALLBACK


def limpar_cache() -> None:
    """Invalida o cache do loader — usado em testes que mexem no arquivo."""
    carregar_tabela.cache_clear()
