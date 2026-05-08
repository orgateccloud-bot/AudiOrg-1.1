"""Catálogo de Tipologias de Anomalias AN-01..AN-18"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class TipologiaAnomalia:
    codigo: str
    nome: str
    eixo: str
    severidade: str          # CRÍTICO | ALTO | MÉDIO | BAIXO
    descricao: str
    cruzamentos: list

CATALOGO: dict[str, TipologiaAnomalia] = {
    "AN-01": TipologiaAnomalia("AN-01","Smurfing Rural","Fragmentação",
        "CRÍTICO","Fracionamento intencional para evitar teto ou rastreabilidade",
        ["GTA","Tabela SENAR","SINTEGRA"]),
    "AN-02": TipologiaAnomalia("AN-02","Carrossel Fiscal","Circularidade",
        "CRÍTICO","Operações circulares para geração artificial de crédito ICMS/Funrural",
        ["SPED","SINTEGRA","RFB CNPJ"]),
    "AN-03": TipologiaAnomalia("AN-03","Nota Fria / Fantasma","Documento",
        "CRÍTICO","NFA-e sem lastro físico ou IE inativa/cancelada",
        ["SEFAZ-GO GIEF","RFB CPF","GTA"]),
    "AN-04": TipologiaAnomalia("AN-04","Subfaturamento","Preço",
        "ALTO","Preço declarado abaixo de 70% do mercado",
        ["CEPEA","SENAR","EMBRAPA preços"]),
    "AN-05": TipologiaAnomalia("AN-05","Superfaturamento","Preço",
        "ALTO","Preço acima de 130% do mercado para inflar custos",
        ["CEPEA","B3 indicadores"]),
    "AN-06": TipologiaAnomalia("AN-06","CFOP Indevido","Classificação",
        "ALTO","CFOP incompatível com operação real ou natureza declarada",
        ["SPED","Tabela CFOP SEFAZ"]),
    "AN-07": TipologiaAnomalia("AN-07","Trânsito Não Realizado","Documento",
        "ALTO","Remessa para leilão sem contra-nota de arremate (NF-e modelo 55)",
        ["ACTs","Leiloeiro","Cartório"]),
    "AN-08": TipologiaAnomalia("AN-08","Transferência Intrafamiliar","Relacionamento",
        "MÉDIO","Operação entre familiares sem preço de mercado",
        ["CAEPF","CRI","Comprovante bancário"]),
    "AN-09": TipologiaAnomalia("AN-09","IE Inativa","Documento",
        "CRÍTICO","Nota emitida com Inscrição Estadual cancelada ou suspensa",
        ["SEFAZ-GO CADESP","RFB CNPJ"]),
    "AN-10": TipologiaAnomalia("AN-10","Período Suspeito","Temporal",
        "MÉDIO","Operações concentradas em fins de semana, feriados ou datas atípicas",
        ["GIEF datas","GTA datas"]),
    "AN-11": TipologiaAnomalia("AN-11","Volume Incompatível","Produtivo",
        "ALTO","Cabeças vendidas incompatíveis com capacidade produtiva declarada",
        ["ITR área","SNCR rebanho","CAR"]),
    "AN-12": TipologiaAnomalia("AN-12","Caixa Dois Agropecuário","Fiscal",
        "CRÍTICO","Receitas não declaradas no LCDPR ou incompatíveis com patrimônio",
        ["LCDPR","DIRPF","ECF"]),
    "AN-13": TipologiaAnomalia("AN-13","Concentração Atípica","Distribuição",
        "ALTO","Poucos destinatários recebem >80% da produção total",
        ["SINTEGRA","SPED","GIEF"]),
    "AN-14": TipologiaAnomalia("AN-14","Devolução Sistemática","Operacional",
        "ALTO","Devoluções repetidas com mesmo emissor dentro de 30 dias",
        ["GIEF devoluções","NF-e modelo 55"]),
    "AN-15": TipologiaAnomalia("AN-15","Funrural Subdeclarado","Previdenciário",
        "ALTO","Base de cálculo Funrural menor que F1 declarado no LCDPR",
        ["LCDPR","CNIS","RFB DCTF"]),
    "AN-16": TipologiaAnomalia("AN-16","ITR Divergente","Patrimonial",
        "MÉDIO","Área declarada no ITR incompatível com volume de produção",
        ["SNCR","CAR","INCRA CCIR"]),
    "AN-17": TipologiaAnomalia("AN-17","Sobreposição de Períodos","Temporal",
        "MÉDIO","Mesma operação declarada em dois períodos fiscais distintos",
        ["SPED ECF","GIEF","LCDPR"]),
    "AN-18": TipologiaAnomalia("AN-18","Ausência de GTA","Documental",
        "ALTO","Movimentação de animais vivos sem Guia de Trânsito Animal correspondente",
        ["AGESGO","MAPA","GTA digital"]),
}

def buscar_por_codigo(codigo: str) -> Optional[TipologiaAnomalia]:
    return CATALOGO.get(codigo.upper())

def listar_criticos() -> list:
    return [a for a in CATALOGO.values() if a.severidade == "CRÍTICO"]
