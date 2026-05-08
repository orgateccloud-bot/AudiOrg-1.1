"""
nfa_ai_schemas.py
═════════════════
Schemas Pydantic V2 para o parser semântico de NFA-e SEFAZ-GO (GIEF).

Compatível com:
  • src/domain/extractor.py  (NFA / Parte / Produto)  — conversão direta via .to_nfa()
  • src/application/reports/orgaudi/orgaudi_adapter.py — aceito por gerar_laudo_orgaudi()

Confiança (0–1):
  1.0  → extração via regex, sem ambiguidade
  0.75 → regex com campos incompletos, completado por Claude
  0.5  → Claude único responsável (regex falhou)
  < 0.5 → nota descartada (campos obrigatórios ausentes)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Naturezas válidas (alinhadas com OrgAudi NaturezaNota) ─────────────────
NaturezaStr = Literal["VENDA", "REMESSA", "LEILAO", "TRANSFERENCIA", "COMPRA", "OUTRAS"]


# ─── Sub-modelos ─────────────────────────────────────────────────────────────

class ParteAI(BaseModel):
    """Remetente ou Destinatário."""
    nome:      str = ""
    cpf_cnpj:  str = ""
    municipio: str = ""
    ie:        str = ""

    @field_validator("cpf_cnpj", mode="before")
    @classmethod
    def limpar_doc(cls, v: str | None) -> str:
        """Remove máscara; aceita CPF (11) ou CNPJ (14)."""
        import re
        return re.sub(r"\D", "", str(v or ""))


class ProdutoAI(BaseModel):
    """Item de gado ou outro bem na nota."""
    codigo:       str   = ""
    descricao:    str   = ""
    quantidade:   float = Field(default=0.0, ge=0)
    vlr_unitario: float = Field(default=0.0, ge=0)
    vlr_total:    float = Field(default=0.0, ge=0)
    vlr_icms:     float = Field(default=0.0, ge=0)


# ─── Nota Fiscal Avulsa extraída (resultado do parser) ───────────────────────

class NFAExtraida(BaseModel):
    """
    NFA-e estruturada, pronta para injeção no OrgAudi.
    Compatível com o modelo NFA do nfa-repo.
    """
    numero:        str         = ""
    emissao:       str         = ""          # DD/MM/YYYY
    natureza:      NaturezaStr = "OUTRAS"
    valor_total:   Decimal     = Decimal("0")
    valor_icms:    Decimal     = Decimal("0")
    chave_acesso:  str         = ""
    local_emissao: str         = ""

    remetente:    ParteAI        = Field(default_factory=ParteAI)
    destinatario: ParteAI        = Field(default_factory=ParteAI)
    produtos:     list[ProdutoAI] = Field(default_factory=list)

    # Metadados do parser — NÃO vão para o laudo
    confianca:      float = Field(default=1.0, ge=0.0, le=1.0)
    origem_extracao: Literal["regex", "claude", "regex+claude"] = "regex"

    @field_validator("valor_total", "valor_icms", mode="before")
    @classmethod
    def parse_decimal(cls, v) -> Decimal:
        if isinstance(v, (int, float)):
            return Decimal(str(v))
        if isinstance(v, str):
            v = v.replace(".", "").replace(",", ".")
            try:
                return Decimal(v)
            except Exception:
                return Decimal("0")
        return Decimal(str(v or 0))

    @property
    def quantidade_total(self) -> float:
        """Soma de cabeças de todos os produtos."""
        return sum(p.quantidade for p in self.produtos)

    def to_nfa(self):
        """Converte para NFA do nfa-repo (compatibilidade com pipeline existente)."""
        from nfa_repo_compat import NFA, Parte, Produto  # lazy import
        return NFA(
            numero=self.numero,
            natureza=self.natureza,
            emissao=self.emissao,
            valor_total=float(self.valor_total),
            valor_icms=float(self.valor_icms),
            quantidade_total=self.quantidade_total,
            chave_acesso=self.chave_acesso or None,
            local_emissao=self.local_emissao or None,
            remetente=Parte(
                nome=self.remetente.nome,
                cpf_cnpj=self.remetente.cpf_cnpj or None,
                municipio=self.remetente.municipio or None,
                ie=self.remetente.ie or None,
            ),
            destinatario=Parte(
                nome=self.destinatario.nome,
                cpf_cnpj=self.destinatario.cpf_cnpj or None,
                municipio=self.destinatario.municipio or None,
                ie=self.destinatario.ie or None,
            ),
            produtos=[
                Produto(
                    codigo=p.codigo,
                    descricao=p.descricao,
                    quantidade=p.quantidade,
                    vlr_total=p.vlr_total,
                    vlr_unitario=p.vlr_unitario,
                    vlr_icms=p.vlr_icms,
                )
                for p in self.produtos
            ],
        )


# ─── Resultado da extração de um PDF completo ────────────────────────────────

class ResultadoExtracaoPDF(BaseModel):
    """Resposta do endpoint POST /nfa/parse."""
    notas:          list[NFAExtraida]
    nome_produtor:  str = ""
    cpf_produtor:   str = ""
    periodo_inicio: str = ""   # DD/MM/YYYY (menor data)
    periodo_fim:    str = ""   # DD/MM/YYYY (maior data)

    # Estatísticas
    total_extraidas: int = 0
    por_regex:       int = 0
    por_claude:      int = 0
    descartadas:     int = 0
    erros:           list[str] = Field(default_factory=list)

    # Custo Claude (tokens consumidos)
    tokens_input:  int = 0
    tokens_output: int = 0

    @model_validator(mode="after")
    def calcular_totais(self) -> "ResultadoExtracaoPDF":
        self.total_extraidas = len(self.notas)
        self.por_regex  = sum(1 for n in self.notas if n.origem_extracao == "regex")
        self.por_claude = sum(1 for n in self.notas if "claude" in n.origem_extracao)

        datas = []
        for n in self.notas:
            try:
                from datetime import datetime
                datas.append(datetime.strptime(n.emissao, "%d/%m/%Y"))
            except ValueError:
                pass
        if datas:
            self.periodo_inicio = min(datas).strftime("%d/%m/%Y")
            self.periodo_fim    = max(datas).strftime("%d/%m/%Y")
        return self


# ─── Schema do tool_use Claude (JSON Schema) ────────────────────────────────
# Enviado como "tools" na chamada à API Anthropic.

TOOL_EXTRAIR_NOTAS = {
    "name": "extrair_notas_nfa",
    "description": (
        "Extrai dados estruturados de blocos de texto de Notas Fiscais Avulsas "
        "Eletrônicas (NFA-e) do GIEF/SEFAZ-GO. Retorna lista de notas com todos "
        "os campos obrigatórios. Use os valores EXATOS do texto — não invente dados."
    ),
    "input_schema": {
        "type": "object",
        "required": ["notas"],
        "properties": {
            "notas": {
                "type": "array",
                "description": "Lista de NFA-e extraídas do texto",
                "items": {
                    "type": "object",
                    "required": ["numero", "emissao", "natureza", "valor_total",
                                 "remetente_nome", "remetente_cpf_cnpj",
                                 "destinatario_nome", "destinatario_cpf_cnpj"],
                    "properties": {
                        "numero": {
                            "type": "string",
                            "description": "Número da NFA (6–10 dígitos)"
                        },
                        "emissao": {
                            "type": "string",
                            "description": "Data de emissão no formato DD/MM/YYYY"
                        },
                        "natureza": {
                            "type": "string",
                            "enum": ["VENDA", "REMESSA", "LEILAO",
                                     "TRANSFERENCIA", "COMPRA", "OUTRAS"],
                            "description": (
                                "Natureza da operação. "
                                "REMESSA/LEILAO → LEILAO. "
                                "OUTRA REMESSAS → REMESSA. "
                                "TRANSFERÊNCIA → TRANSFERENCIA."
                            )
                        },
                        "valor_total": {
                            "type": "number",
                            "description": "Valor total da nota em reais (float)"
                        },
                        "valor_icms": {
                            "type": "number",
                            "description": "Valor do ICMS (0 se isento)",
                            "default": 0.0
                        },
                        "chave_acesso": {
                            "type": "string",
                            "description": "Chave de acesso com 44 dígitos (se presente)",
                            "default": ""
                        },
                        "remetente_nome": {
                            "type": "string",
                            "description": "Nome/razão social do remetente"
                        },
                        "remetente_cpf_cnpj": {
                            "type": "string",
                            "description": "CPF ou CNPJ do remetente (somente dígitos)"
                        },
                        "remetente_municipio": {
                            "type": "string",
                            "description": "Município do remetente",
                            "default": ""
                        },
                        "remetente_ie": {
                            "type": "string",
                            "description": "Inscrição Estadual do remetente",
                            "default": ""
                        },
                        "destinatario_nome": {
                            "type": "string",
                            "description": "Nome/razão social do destinatário"
                        },
                        "destinatario_cpf_cnpj": {
                            "type": "string",
                            "description": "CPF ou CNPJ do destinatário (somente dígitos)"
                        },
                        "destinatario_municipio": {
                            "type": "string",
                            "description": "Município do destinatário",
                            "default": ""
                        },
                        "produtos": {
                            "type": "array",
                            "description": "Itens da nota (gado bovino ou outros bens)",
                            "default": [],
                            "items": {
                                "type": "object",
                                "properties": {
                                    "codigo":       {"type": "string", "default": ""},
                                    "descricao":    {"type": "string"},
                                    "quantidade":   {"type": "number", "default": 0},
                                    "vlr_unitario": {"type": "number", "default": 0},
                                    "vlr_total":    {"type": "number", "default": 0},
                                    "vlr_icms":     {"type": "number", "default": 0}
                                },
                                "required": ["descricao"]
                            }
                        }
                    }
                }
            }
        }
    }
}
