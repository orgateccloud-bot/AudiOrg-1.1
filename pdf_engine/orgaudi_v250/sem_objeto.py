"""
orgaudi_v250.sem_objeto
═══════════════════════
Variante do laudo v2.5.0 para o caso "auditoria sem objeto":
contribuinte cadastrado mas com zero NFA-e no período.

Usa exatamente o mesmo pipeline visual (Manrope · #0B3B5C/#14B8A6 ·
capa editorial com gradiente · Chrome headless), apenas com um `ctx`
montado manualmente — sem passar por `_preparar_ctx`, que exige
`NotaFiscal` válida.

Uso direto:
    from pdf_engine.orgaudi_v250 import gerar_laudo_sem_objeto_v250
    gerar_laudo_sem_objeto_v250("HELLIDA", "024.979.491-82", Path("..."))

Também é chamada automaticamente por `gerar_laudo_v250()` quando
`notas == []`, em vez de retornar sem gerar PDF.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .renderer import html_para_pdf
from .template_builder import construir_html

logger = logging.getLogger("orgaudi")


def _hash_sem_objeto(nome: str, cpf: str, periodo_str: str) -> str:
    base = f"{nome}|{cpf}|sem_objeto|{periodo_str}|OrgAudi-v2.5.0"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _fmt_cpf(cpf: str) -> str:
    c = re.sub(r"\D", "", cpf)
    if len(c) == 11:
        return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cpf


def _construir_ctx_sem_objeto(
    nome: str,
    cpf: str,
    municipio: str,
    estado: str,
    periodo_inicio: date,
    periodo_fim: date,
) -> dict:
    """Monta o ctx para o template v250 no cenário 'sem objeto'."""
    cpf_limpo = re.sub(r"\D", "", cpf)
    cpf_fmt = _fmt_cpf(cpf)
    periodo_str = f"{periodo_inicio.strftime('%d/%m/%Y')} a {periodo_fim.strftime('%d/%m/%Y')}"
    hash_doc = _hash_sem_objeto(nome, cpf_limpo, periodo_str)

    achados = [
        {
            "codigo": "T-00",
            "titulo": "Auditoria sem objeto — nenhuma NFA-e no período",
            "descricao": (
                "Os documentos fiscais recebidos para este contribuinte no exercício "
                "auditado <b>não apresentam Notas Fiscais Avulsas (NFA-e) emitidas ou "
                "recebidas</b>. O extrato consultado contém apenas o cabeçalho cadastral, "
                "sem transações no período."
            ),
            "severidade_key": "ATENCAO",
            "tabela_cabecalhos": ["Posição", "Arquivo origem", "NFA-e extraídas"],
            "tabela_linhas": [
                ["REMETENTE",    f"PDF SEFAZ-GO · {periodo_fim.year}", "0"],
                ["DESTINATÁRIO", f"PDF SEFAZ-GO · {periodo_fim.year}", "0"],
            ],
            "tabela_totais": ["TOTAL", "2 arquivos", "0"],
            "cruzamentos": [
                f"Verificar com o produtor se houve emissão de NFA-e em {periodo_fim.year}.",
                "Confirmar com a SEFAZ-GO se o cadastro do produtor permanece ativo.",
                "Solicitar reextração dos NFE completos ao escritório contábil se houver "
                "expectativa de movimentação.",
            ],
            "porque_critico": (
                "Sem documentos auditáveis, o pipeline Horizon-Blue One não acionou "
                "agentes LLM (S1..S7). Custo de tokens associado: USD 0,00. "
                "O laudo permanece no acervo como evidência de exercício sem operação."
            ),
        }
    ]

    resumo = {
        "periodo_str":        periodo_str,
        "receita_fmt":        "R$ 0,00",
        "remessas_fmt":       "R$ 0,00",
        "compras_fmt":        "R$ 0,00",
        "funrural_fmt":       "R$ 0,00",
        "aliq_funrural":      "1,50%",
        "notas_vendas":       0,
        "notas_remessas":     0,
        "notas_compras":      0,
        "valor_bruto_saidas": "0",
    }

    contrib = {
        "nome":        nome,
        "cpf":         cpf_limpo,
        "cpf_fmt":     cpf_fmt,
        "ie":          "—",
        "municipio":   municipio,
        "estado":      estado,
        "periodo_str": periodo_str,
    }

    recomendacoes = [
        {
            "titulo":    "Confirmar ausência de emissão",
            "descricao": f"Conferir com o produtor se houve emissão de NFA-e em {periodo_fim.year}.",
            "prazo":     "30 dias",
        },
        {
            "titulo":    "Validar cadastro SEFAZ-GO",
            "descricao": "Verificar se o cadastro do produtor permanece ativo no GIEF/SEFAZ-GO.",
            "prazo":     "30 dias",
        },
        {
            "titulo":    "Registrar exercício sem operação",
            "descricao": (
                f"Caso confirmada a ausência, anotar 'sem operação {periodo_fim.year}' no "
                "controle interno e dispensar a auditoria detalhada do período."
            ),
            "prazo":     "Imediato",
        },
        {
            "titulo":    "Reprocessar se houver dados",
            "descricao": "Se novos NFE forem disponibilizados, reprocessar individualmente via "
                         "scripts/auditar_lote_completo_pdf.py.",
            "prazo":     "Sob demanda",
        },
    ]

    return {
        "contribuinte":      contrib,
        "periodo":           {"inicio": periodo_inicio, "fim": periodo_fim},
        "resumo":            resumo,
        "achados":           achados,
        "planilha_vendas":   [],
        "planilha_remessas": [],
        "planilha_compras":  [],
        "recomendacoes":     recomendacoes,
        "sev_key":           "ATENCAO",
        "sev_label":         "SEM OBJETO",
        "n_achados":         1,
        "n_criticos":        0,
        "n_altos":           0,
        "n_medios":          0,
        "n_atencao":         1,
        "n_conformes":       0,
        "hash_doc":          hash_doc,
        # capa(1) + resumo(2) + achados MEDIO/ATENCAO(3) + assinatura(4)
        "total_pages":       4,
    }


def gerar_laudo_sem_objeto_v250(
    cliente_nome: str,
    cliente_cpf: str,
    saida: Path,
    municipio: str = "Formoso",
    estado: str = "GO",
    periodo_inicio: Optional[date] = None,
    periodo_fim: Optional[date] = None,
) -> None:
    """
    Gera o laudo v2.5.0 para o cenário 'auditoria sem objeto'.

    Mesma identidade visual dos demais laudos do lote (mesmo template HTML/CSS,
    fontes, paleta, capa editorial). Diferenças:
      - Sem KPIs financeiros (zero notas)
      - Achado único T-00 em severidade ATENÇÃO
      - 4 páginas (vs 5-6 dos laudos com NFAs)

    Parâmetros
    ----------
    cliente_nome   : nome completo do contribuinte
    cliente_cpf    : CPF (com ou sem pontuação)
    saida          : caminho do PDF de saída
    municipio      : município (default Formoso)
    estado         : UF (default GO)
    periodo_inicio : data de início do período (default 01/01 do ano corrente)
    periodo_fim    : data de fim do período (default 31/12 do ano corrente)
    """
    if periodo_inicio is None:
        periodo_inicio = date(date.today().year, 1, 1)
    if periodo_fim is None:
        periodo_fim = date(date.today().year, 12, 31)

    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Gerando laudo v250 SEM OBJETO: %s → %s", cliente_nome, saida.name)

    ctx = _construir_ctx_sem_objeto(
        cliente_nome, cliente_cpf, municipio, estado, periodo_inicio, periodo_fim,
    )
    html = construir_html(ctx)
    html_para_pdf(html, saida)

    logger.info("Laudo v250 (sem objeto) gerado: %s (%.1f KB)",
                saida.name, saida.stat().st_size / 1024)
