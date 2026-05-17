"""
api/schemas/cruzamento.py
═════════════════════════
Schemas Pydantic para o fluxo de Auditoria Cruzada (Planilha IR v5 × PDF GIEF).

Usados por:
  - api/routes/auditoria_cruzada.py  (endpoints HTTP)
  - scripts/gerar_laudos.py          (geração em lote, sem HTTP)
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class TotaisFonte(BaseModel):
    """Indicadores agregados de uma fonte (Planilha IR v5 OU PDF GIEF)."""

    volume_bruto_saidas: Optional[Decimal] = None
    receita_imediata: Optional[Decimal] = None
    transito_remessas: Optional[Decimal] = None
    cabecas_totais: Optional[int] = None
    qtd_vendas: Optional[int] = None
    qtd_remessas: Optional[int] = None
    qtd_compras: Optional[int] = None
    valor_compras: Optional[Decimal] = None


class PlanilhaMensalInput(BaseModel):
    """Linha mensal para geração do .docx da Planilha IR v5."""

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
    """Payload completo para auditoria cruzada — HTTP e geração em lote."""

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
    totais_planilha: TotaisFonte
    totais_pdf_gief: TotaisFonte
    vendas_mensais: List[PlanilhaMensalInput] = Field(default_factory=list)
    remessas_mensais: List[PlanilhaMensalInput] = Field(default_factory=list)
    compras_mensais: List[PlanilhaMensalInput] = Field(default_factory=list)
    funrural_estimado: Optional[Decimal] = None
    aliquota_funrural_pct: str = "1,50%"
    achados_criticos: List[AchadoCriticoInput] = Field(default_factory=list)
