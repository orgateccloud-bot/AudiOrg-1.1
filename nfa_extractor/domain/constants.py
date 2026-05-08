"""Constantes globais do projeto NFA Extractor — fonte única da verdade."""

import re

# ─── Paleta de Cores (hex sem #) ──────────────────────────────────────────────
CORES = {
    'BG':       '080C14',  # Obsidian Black
    'BG2':      '111827',  # Deep Navy Blue
    'BG3':      '1F2937',  # Slate Navy
    'BG4':      '374151',  # Slate Grey
    'BORDER':   '27272A',  # Zinc 800
    'CYAN':     '38BDF8',  # Sky 400
    'PRIMARY':  '6366F1',  # Indigo 500
    'GREEN':    '10B981',  
    'ORANGE':   'F59E0B',  
    'RED':      'EF4444',  
    'TEXT':     'F8FAFC',
    'TEXT_DIM': '94A3B8',
    'WHITE':    'FFFFFF',
    'GRAY':     '64748B',
}

def hex_cor(nome_cor: str) -> str:
    """Retorna a cor com # para UI (CustomTkinter/Matplotlib/ReportLab)."""
    return f"#{CORES[nome_cor]}"

# ─── Larguras de colunas Excel ────────────────────────────────────────────────
LARGURAS_EXCEL = {
    'notas': [12, 12, 18, 28, 36, 16, 20, 28, 10, 16, 50],
    'itens': [10, 12, 16, 34, 16, 20, 8, 50, 8, 14, 12, 14],
    'dest':  [38, 16, 20, 10, 12, 16, 16],
    'mensal': [14, 12, 12, 16],
}

# ─── Cabeçalhos Excel ─────────────────────────────────────────────────────────
CABECALHOS_EXCEL = {
    'notas': [
        'Num NFA', 'Emissão', 'Natureza', 'Local Emissão', 'Destinatário',
        'CPF/CNPJ Dest', 'Município Dest', 'Transportador', 'Cabeças',
        'Valor Total', 'Chave de Acesso',
    ],
    'itens': [
        'NFA', 'Emissão', 'Natureza', 'Destinatário', 'CPF/CNPJ', 'Município',
        'Código', 'Descrição', 'Qtd', 'Vlr Unit', 'Vlr ICMS', 'Vlr Total',
    ],
    'dest': [
        'Destinatário', 'CPF/CNPJ', 'Município', 'Notas',
        'Cabeças', 'Valor Total', 'Ticket Médio',
    ],
    'mensal': ['Mês/Ano', 'Qtd Notas', 'Cabeças', 'Valor Total'],
}

# ─── Padrões Regex ────────────────────────────────────────────────────────────
REGEX = {
    'chave_acesso':   re.compile(r'^\d{44}$'),
    'cpf':            re.compile(r'\d{3}\.\d{3}\.\d{3}-\d{2}'),
    'cnpj':           re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'),
    'cpf_ou_cnpj':    re.compile(r'(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})'),
    'numero_nota':    re.compile(r'^(\d{6,10})\s+(\d{2}/\d{2}/\d{4})\s+(.+)$'),
    'ie_no_fim':      re.compile(r'(\d{6,12})\s*$'),
    'identificacao':  re.compile(r'IDENTIFICA[ÇC][ÃA]O DA NOTA', re.IGNORECASE),
    'agencia':        re.compile(r'AGENCIA FAZENDARIA|NOTA EMITIDA PELO', re.IGNORECASE),
    'remetente':      re.compile(r'REMETENTE', re.IGNORECASE),
    'destinatario':   re.compile(r'DESTINAT[AÁ]RIO', re.IGNORECASE),
    'transportador':  re.compile(r'TRANSPORTADOR', re.IGNORECASE),
    'descricao':      re.compile(r'DESCRI', re.IGNORECASE),
    'produto': re.compile(
        r'^(\d+)\s+(.+?)\s+(\d+[.,]\d+)\s+R\$\s*([\d.,]+)\s+([\d.,]+)\s+R\$\s*([\d.,]+)$'
    ),
}
