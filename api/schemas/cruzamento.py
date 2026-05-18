"""
api/schemas/cruzamento.py
═════════════════════════
Schemas Pydantic para o fluxo de Auditoria GIEF-only (a partir de 2026-05-17).

Histórico:
  - v1 (até 2026-05-16): Auditoria CRUZADA Planilha IR v5 × PDF GIEF.
  - v2 (atual): Auditoria GIEF-only. Dados extraídos exclusivamente do PDF
    GIEF/SEFAZ. Classificação:
      * Estado = GO → usa campo NATUREZA do GIEF (VENDA / REMESSA-LEILAO / OUTRA).
      * Outros estados → usa CFOP (5.101 venda, 5.914 remessa, 1.914 retorno).

  Os campos da Planilha IR v5 (totais_planilha, vendas_mensais, remessas_mensais,
  compras_mensais) foram tornados OPCIONAIS e estão em descontinuação.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class TotaisFonte(BaseModel):
    """Indicadores agregados de uma fonte (GIEF ou — legado — Planilha IR v5)."""

    volume_bruto_saidas: Optional[Decimal] = None
    receita_imediata: Optional[Decimal] = None
    transito_remessas: Optional[Decimal] = None
    cabecas_totais: Optional[int] = None
    qtd_vendas: Optional[int] = None
    qtd_remessas: Optional[int] = None
    qtd_compras: Optional[int] = None
    valor_compras: Optional[Decimal] = None


class PlanilhaMensalInput(BaseModel):
    """[LEGADO] Linha mensal da Planilha IR v5. Mantido só para compat com JSONs antigos."""

    mes: str
    qtd_notas: int = 0
    cabecas: int = 0
    valor: Decimal = Decimal("0")


class AchadoCriticoInput(BaseModel):
    """Achado crítico opcional (C-01, C-10, C-03, A-01)."""

    codigo: str
    titulo: str
    descricao: str
    severidade: str = "CRITICO"
    porque_critico: str = ""
    cruzamentos: List[str] = Field(default_factory=list)
    tabela_cabecalhos: List[str] = Field(default_factory=list)
    tabela_linhas: List[List[str]] = Field(default_factory=list)
    tabela_totais: List[str] = Field(default_factory=list)


class CruzamentoRequest(BaseModel):
    """Payload de auditoria — modo GIEF-only (Planilha IR v5 descontinuada).

    Campos obrigatórios: identificação do contribuinte, período e `totais_pdf_gief`.
    Campos opcionais (legado): `totais_planilha`, `vendas_mensais`, `remessas_mensais`,
    `compras_mensais`. Quando presentes, o pipeline produz o laudo no formato antigo
    (cruzamento + Planilha IR v5). Quando ausentes, o laudo é GIEF-only.
    """

    contribuinte_cpf: str
    contribuinte_nome: str
    contribuinte_ie: str = ""
    municipio: str = ""
    estado: str = "GO"
    periodo_inicio: str
    periodo_fim: str
    documento_base: str = ""
    is_pj: bool = False
    is_segurado_especial: bool = False
    totais_pdf_gief: TotaisFonte
    totais_planilha: Optional[TotaisFonte] = None
    vendas_mensais: List[PlanilhaMensalInput] = Field(default_factory=list)
    remessas_mensais: List[PlanilhaMensalInput] = Field(default_factory=list)
    compras_mensais: List[PlanilhaMensalInput] = Field(default_factory=list)
    funrural_estimado: Optional[Decimal] = None
    aliquota_funrural_pct: str = "1,50%"
    achados_criticos: List[AchadoCriticoInput] = Field(default_factory=list)
