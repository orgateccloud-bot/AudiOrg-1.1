"""Apuração Fiscal Rural — F1–F6, Funrural e IRPF estimado.

Alíquotas FUNRURAL 2026 (corte: 01/04/2026):
  PJ:               2,23% (antes: 2,05%)
  PF:               1,63% (antes: 1,50%)
  Segurado Especial: 1,50% (excepcionado pela RFB 03/2026)

Fórmulas:
  F1 = Receita Imediata (VENDA/RECEITA)
  F2 = Gado em trânsito
  F3 = Receita de leilão
  F4 = F1 + F3
  F5 = F4 - F6  (resultado rural)
  F6 = Despesas dedutíveis (COMPRA/DESPESA)
  FUNRURAL = F1 × alíquota
  IRPF     = max(F5 × 20%, 0)
"""
from dataclasses import asdict, dataclass
from datetime import date
from typing import List


@dataclass
class ResumoFiscal:
    f1_receita_imediata: float = 0.0
    f2_transito: float         = 0.0
    f3_receita_leilao: float   = 0.0
    f4_receita_bruta: float    = 0.0
    f5_resultado_rural: float  = 0.0
    f6_despesa: float          = 0.0
    funrural: float            = 0.0
    irpf_estimado: float       = 0.0
    aliquota_funrural: float   = 0.0
    total_notas: int           = 0

    def to_dict(self) -> dict:
        return asdict(self)


def apurar_resumo(
    notas: List[dict],
    eh_pj: bool = False,
    eh_segurado_especial: bool = False,
    data_referencia: date | None = None,
) -> ResumoFiscal:
    if data_referencia is None:
        data_referencia = date.today()

    corte = date(2026, 4, 1)
    if eh_pj:
        aliq = 0.0223 if data_referencia >= corte else 0.0205
    elif eh_segurado_especial:
        aliq = 0.0150
    else:
        aliq = 0.0163 if data_referencia >= corte else 0.0150

    r = ResumoFiscal(aliquota_funrural=aliq, total_notas=len(notas))

    for n in notas:
        cat = (n.get("categoria_contabil") or n.get("natureza_exibicao", "")).upper()
        val = float(n.get("valor_total", 0))
        if cat == "RECEITA":
            r.f1_receita_imediata += val
        elif cat in ("TRANSITO", "TRÂNSITO", "TRANSIT"):
            r.f2_transito += val
        elif cat == "DESPESA":
            r.f6_despesa += val

    r.f4_receita_bruta   = r.f1_receita_imediata + r.f3_receita_leilao
    r.f5_resultado_rural = r.f4_receita_bruta - r.f6_despesa
    r.funrural           = round(r.f1_receita_imediata * aliq, 2)
    r.irpf_estimado      = round(max(r.f5_resultado_rural * 0.20, 0), 2)
    return r
