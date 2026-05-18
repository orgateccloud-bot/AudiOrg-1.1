"""
orgaudi.domain
══════════════
Enums (Severidade, NaturezaNota, CategoriaContabil) e dataclasses de entrada
do sistema (Contribuinte, Periodo, NotaFiscal, Achado, Etapa, etc.).

Este módulo define o "vocabulário" do domínio. Não tem lógica de
processamento — só validação de coerência interna dos próprios dataclasses.

Dependências internas: orgaudi.validators (para validação de CPF/CNPJ na
construção do Contribuinte e parsing de strings).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .validators import (
    mascara_cpf,
    mascara_cnpj,
    validar_cpf,
    validar_cnpj,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class Severidade(str, Enum):
    CRITICO = "CRITICO"
    ALTO = "ALTO"
    MEDIO = "MEDIO"
    ATENCAO = "ATENCAO"
    CONFORME = "CONFORME"


class NaturezaNota(str, Enum):
    VENDA = "VENDA"
    REMESSA = "REMESSA"
    LEILAO = "LEILAO"
    COMPRA = "COMPRA"
    TRANSFERENCIA = "TRANSFERENCIA"


class CategoriaContabil(str, Enum):
    """Resultado da Regra 1 OrgAudi 1.0."""
    RECEITA = "RECEITA"           # Remetente + Venda
    TRANSITO = "TRANSITO"         # Remetente + Remessa/Leilão
    DESPESA = "DESPESA"           # Destinatário + Compra
    TRANSFERENCIA = "TRANSFERENCIA"  # Mesmo CPF nos dois lados


# ═══════════════════════════════════════════════════════════════════════════════
#  DATACLASSES DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Contribuinte:
    """Identificação do contribuinte auditado.

    Categorias previdenciárias rurais (afetam a alíquota Funrural — LC 224/2025):
      - eh_pj=False, eh_segurado_especial=False (default): produtor rural PF patronal
        → 1,5% até 31/03/2026 ; 1,63% a partir de 01/04/2026
      - eh_pj=False, eh_segurado_especial=True: agricultor familiar / segurado especial
        → 1,5% mantida (orientação RFB de 03/2026, após articulação do MDA)
      - eh_pj=True: produtor rural pessoa jurídica
        → 2,05% até 31/03/2026 ; 2,23% a partir de 01/04/2026
    """
    nome: str
    cpf: str  # com ou sem máscara — será normalizado
    ie: str = ""
    municipio: str = ""
    estado: str = "GO"
    eh_pj: bool = False
    eh_segurado_especial: bool = False

    def __post_init__(self):
        # Mascara CPF (11 dígitos) ou CNPJ (14 dígitos) conforme o caso
        doc_num = re.sub(r"\D", "", self.cpf)
        if len(doc_num) == 14:
            self.cpf = mascara_cnpj(self.cpf)
            self.eh_pj = True
        else:
            self.cpf = mascara_cpf(self.cpf)
        # Validação de coerência entre flags
        if self.eh_pj and self.eh_segurado_especial:
            raise ValueError(
                "Contribuinte não pode ser PJ e segurado especial simultaneamente. "
                "Segurado especial é categoria exclusiva de PF (agricultor familiar).")

    @property
    def cpf_valido(self) -> bool:
        doc_num = re.sub(r"\D", "", self.cpf)
        if len(doc_num) == 14:
            return validar_cnpj(self.cpf)
        return validar_cpf(self.cpf)

    @property
    def categoria_previdenciaria(self) -> str:
        """Rótulo legível da categoria — usado em laudos e mensagens."""
        if self.eh_pj:
            return "PJ"
        if self.eh_segurado_especial:
            return "PF Segurado Especial"
        return "PF Patronal"


@dataclass
class Periodo:
    """Período auditado."""
    inicio: date
    fim: date
    data_auditoria: date = field(default_factory=date.today)

    def __post_init__(self):
        # Aceita strings ISO
        if isinstance(self.inicio, str):
            self.inicio = datetime.strptime(self.inicio, "%Y-%m-%d").date()
        if isinstance(self.fim, str):
            self.fim = datetime.strptime(self.fim, "%Y-%m-%d").date()
        if isinstance(self.data_auditoria, str):
            self.data_auditoria = datetime.strptime(self.data_auditoria, "%Y-%m-%d").date()


@dataclass
class NotaFiscal:
    """Uma NFA-e individual. Todas as outras estatísticas derivam disto.

    Campos `ie_*` e `municipio_*` são opcionais (foram introduzidos para
    suportar o teste T-05 IE Inconsistente). Notas legadas sem esses campos
    seguem funcionando normalmente.
    """
    numero: str
    data: date
    natureza: NaturezaNota
    valor: Decimal
    cabecas: int = 0
    remetente_cpf: str = ""
    remetente_nome: str = ""
    destinatario_cpf: str = ""
    destinatario_nome: str = ""
    # Campos cadastrais opcionais (usados em T-05 IE inconsistente e A-02)
    ie_remetente: str = ""
    ie_destinatario: str = ""
    municipio_destinatario: str = ""

    def __post_init__(self):
        if isinstance(self.data, str):
            self.data = datetime.strptime(self.data, "%Y-%m-%d").date()
        if not isinstance(self.valor, Decimal):
            self.valor = Decimal(str(self.valor))
        if isinstance(self.natureza, str):
            self.natureza = NaturezaNota(self.natureza)


@dataclass
class Leiloeiro:
    """Leiloeiro com gado em trânsito não-arrematado."""
    nome: str
    cnpj: str
    qtd_notas: int
    valor_total: Decimal


@dataclass
class PFRecorrente:
    """PF que aparece como destinatário 3+ vezes (T-04)."""
    nome: str
    cpf: str
    qtd_notas: int
    valor_total: Decimal


@dataclass
class Achado:
    """Um achado da auditoria — classificado por severidade."""
    codigo: str               # C-01, A-01, M-01, AT-01
    titulo: str
    descricao: str
    severidade: Severidade
    cruzamentos: list[str] = field(default_factory=list)
    tabela_cabecalhos: list[str] = field(default_factory=list)
    tabela_linhas: list[list[str]] = field(default_factory=list)
    tabela_totais: list[str] = field(default_factory=list)
    porque_critico: str = ""

    def __post_init__(self):
        if isinstance(self.severidade, str):
            self.severidade = Severidade(self.severidade)


@dataclass
class Etapa:
    """Etapa do plano de ação (timeline)."""
    numero: int
    titulo: str
    prazo: str               # "30 DIAS"
    accent: Severidade       # cor
    itens: list[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.accent, str):
            self.accent = Severidade(self.accent)


# ═══════════════════════════════════════════════════════════════════════════════
#  EXCEÇÕES DE DOMÍNIO
# ═══════════════════════════════════════════════════════════════════════════════

class CPFInvalidoError(ValueError):
    """Erro de validação de CPF — abortar geração do laudo."""
    pass
