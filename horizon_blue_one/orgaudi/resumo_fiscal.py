"""Apuração Fiscal Rural — F1–F6, Funrural e IRPF estimado.

As alíquotas FUNRURAL e IRPF vivem em `data/funrural_aliquotas.yaml`,
carregadas via `aliquotas_loader.carregar_tabela()` (com fallback hard-coded
para resiliência). Mudanças de alíquota → editar o YAML + bump de versão.

Fórmulas:
  F1 = Receita Imediata (VENDA/RECEITA)
  F2 = Gado em trânsito
  F3 = Receita de leilão
  F4 = F1 + F3
  F5 = F4 - F6  (resultado rural)
  F6 = Despesas dedutíveis (COMPRA/DESPESA)
  FUNRURAL = F1 × alíquota (tabela)
  IRPF     = max(F5 × alíquota_irpf, 0)
"""
from dataclasses import dataclass, asdict
from datetime import date
from typing import List

from .aliquotas_loader import carregar_tabela


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

    tabela = carregar_tabela()
    aliq = tabela.aliquota(
        eh_pj=eh_pj,
        eh_segurado_especial=eh_segurado_especial,
        data_referencia=data_referencia,
    )

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
    r.irpf_estimado      = round(max(r.f5_resultado_rural * tabela.irpf_resultado_rural, 0), 2)
    return r
