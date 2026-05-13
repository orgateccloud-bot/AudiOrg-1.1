"""
pdf_engine.orgaudi.report_builder
═════════════════════════════════
Ponto de entrada do laudo OrgAudi v2.5.0 (motor HTML/Chrome — padrão).

Interface pública:
    from pdf_engine import gerar_laudo_v250
    gerar_laudo_v250(notas, cliente_nome, cliente_cpf, saida, municipio, estado)

Arquitetura:
    1. Reutiliza domain + data_processing + validators (mesma pasta)
    2. Converte para ctx dict que o template_builder entende
    3. Gera HTML self-contained (fontes base64)
    4. Renderiza via Chrome headless → PDF

Design: Manrope + JetBrains Mono · #0B3B5C + #14B8A6 · capa editorial com gradiente
"""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .data_processing import (
    apurar_resumo,
    construir_planilha_mensal,
    hash_laudo,
    teste_t01_concentracao,
    teste_t02_smurfing,
    teste_t04_concentracao_pf,
    teste_t07_documental,
)
from .domain import (
    Achado,
    CategoriaContabil,
    Contribuinte,
    NotaFiscal,
    Periodo,
    Severidade,
)
from .validators import fmt_brl, fmt_data, fmt_pct, validar_cpf

from .template_builder import construir_html
from .renderer import html_para_pdf

logger = logging.getLogger("orgaudi")


# ─── Mapeamento Severidade v240 → chave do template v250 ────────────────────
_SEV_MAP = {
    Severidade.CRITICO:  "CRITICO",
    Severidade.ALTO:     "ALTO",
    Severidade.MEDIO:    "MEDIO",
    Severidade.ATENCAO:  "ATENCAO",
    Severidade.CONFORME: "CONFORME",
}

_SEV_LABEL = {
    "CRITICO":  "CRÍTICO",
    "ALTO":     "ALTO",
    "MEDIO":    "MÉDIO",
    "ATENCAO":  "ATENÇÃO",
    "CONFORME": "CONFORME",
}

_SEV_ORDER = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2, "ATENCAO": 3, "CONFORME": 4}


def _fmt_cpf(cpf: str) -> str:
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


def _achado_to_dict(a: Achado) -> dict:
    sev_key = _SEV_MAP.get(a.severidade, "MEDIO")
    return {
        "codigo":            a.codigo,
        "titulo":            a.titulo,
        "descricao":         a.descricao,
        "severidade_key":    sev_key,
        "tabela_cabecalhos": a.tabela_cabecalhos or [],
        "tabela_linhas":     a.tabela_linhas or [],
        "tabela_totais":     a.tabela_totais or None,
        "cruzamentos":       a.cruzamentos or [],
        "porque_critico":    getattr(a, "porque_critico", "") or "",
    }


def _planilha_to_dicts(planilha) -> list[dict]:
    """Converte lista de PlanilhaMensal em lista de dicts para o template.

    PlanilhaMensal.mes é str (ex: "Jan/2025" ou "2025-01") conforme construído pelo v240.
    """
    result = []
    for p in planilha:
        mes_str = str(p.mes)
        result.append({
            "mes":        mes_str,
            "qtd_notas":  p.qtd_notas,
            "cabecas":    p.cabecas,
            "valor":      p.valor,
            "valor_fmt":  fmt_brl(p.valor),
            "valor_acum_fmt": fmt_brl(p.valor),
        })
    return result


def _nivel_risco_geral(achados: list[dict]) -> tuple[str, str]:
    """Retorna (sev_key, sev_label) para o pior nível de achado."""
    for sev in ("CRITICO", "ALTO", "ATENCAO", "MEDIO"):
        if any(a.get("severidade_key") == sev for a in achados):
            return sev, _SEV_LABEL[sev]
    return "CONFORME", "CONFORME"


def _recomendacoes_padrao(achados: list[dict], resumo_dict: dict) -> list[dict]:
    """Gera recomendações padrão baseadas nos achados."""
    recs = []
    if any(a.get("severidade_key") == "CRITICO" for a in achados):
        recs.append({
            "titulo":    "Cruzar GTAs no AGRODEFESA-GO",
            "descricao": "Verificar Guias de Trânsito Animal correspondentes às NFA-e críticas.",
            "prazo":     "60 dias",
        })
    recs.append({
        "titulo":    "Conferir Funrural (GPS mensal)",
        "descricao": "Recolhimento mensal proporcional às vendas diretas a pessoa física.",
        "prazo":     "Conformidade Mensal",
    })
    recs.append({
        "titulo":    "Manter LCDPR atualizado",
        "descricao": "Livro Caixa Digital do Produtor Rural — obrigatório se receita > R$ 75.936,75.",
        "prazo":     "DIRPF 2026",
    })
    if any(a.get("severidade_key") == "ALTO" for a in achados):
        recs.append({
            "titulo":    "Cruzar CAEPF dos PFs recorrentes",
            "descricao": "Verificar cadastro de produtor rural para destinatários com 3+ aquisições.",
            "prazo":     "60 dias",
        })
    return recs[:4]


def _preparar_ctx(
    notas: list[NotaFiscal],
    contribuinte: Contribuinte,
    periodo: Periodo,
) -> dict:
    """
    Executa todo o pipeline de dados e retorna o ctx dict
    pronto para o template_builder.
    """
    # ── Pipeline de dados (reutiliza v240) ──────────────────────────────────
    resumo = apurar_resumo(notas, contribuinte, data_referencia=periodo.fim)

    cpf = contribuinte.cpf
    planilha_vendas   = construir_planilha_mensal(notas, CategoriaContabil.RECEITA,  cpf)
    planilha_remessas = construir_planilha_mensal(notas, CategoriaContabil.TRANSITO, cpf)
    planilha_compras  = construir_planilha_mensal(notas, CategoriaContabil.DESPESA,  cpf)

    t01 = teste_t01_concentracao(notas, cpf)
    t02 = teste_t02_smurfing(notas, cpf)
    t04 = teste_t04_concentracao_pf(notas, cpf)
    t07 = teste_t07_documental(notas)

    hash_doc = hash_laudo(contribuinte, periodo, resumo, notas)

    # ── Sugerir achados (mesma lógica do report_builder_rl) ────────────────
    from .report_builder_rl import LaudoOrgAudi
    laudo_tmp = LaudoOrgAudi(
        contribuinte=contribuinte,
        periodo=periodo,
        notas=notas,
        resumo=resumo,
        t01=t01, t02=t02, t04=t04, t07=t07,
        planilha_vendas=planilha_vendas,
        planilha_remessas=planilha_remessas,
        planilha_compras=planilha_compras,
    )
    achados_v240 = laudo_tmp._sugerir_achados()

    # Converter achados
    achados_dicts = [_achado_to_dict(a) for a in achados_v240]

    # Contagens por severidade
    def _cnt(key):
        return sum(1 for a in achados_dicts if a.get("severidade_key") == key)

    sev_key, sev_label = _nivel_risco_geral(achados_dicts)

    # ── Resumo dict para o template ─────────────────────────────────────────
    resumo_dict = {
        "periodo_str":       f"{fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}",
        "receita_fmt":       fmt_brl(resumo.F4_receita_bruta),
        "remessas_fmt":      fmt_brl(resumo.F2_transito),
        "compras_fmt":       fmt_brl(resumo.F6_despesa),
        "funrural_fmt":      fmt_brl(resumo.funrural),
        "aliq_funrural":     f"{float(resumo.aliquota_funrural) * 100:.2f}%".replace(".", ","),
        "notas_vendas":      resumo.qtd_vendas,
        "notas_remessas":    resumo.qtd_remessas,
        "notas_compras":     resumo.qtd_compras,
        "valor_bruto_saidas": str(resumo.F4_receita_bruta),
    }

    # ── Dados do contribuinte para o template ────────────────────────────────
    contrib_dict = {
        "nome":        contribuinte.nome,
        "cpf":         contribuinte.cpf,
        "cpf_fmt":     _fmt_cpf(contribuinte.cpf),
        "ie":          getattr(contribuinte, "inscricao_estadual", None) or "—",
        "municipio":   getattr(contribuinte, "municipio", "Formoso"),
        "estado":      getattr(contribuinte, "estado", "GO"),
        "periodo_str": f"{fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}",
    }

    # Recomendações
    recs = _recomendacoes_padrao(achados_dicts, resumo_dict)

    # Total de páginas:
    # 1 capa + 1 resumo + páginas_achados + 1 assinatura
    n_pag_achados = sum([
        1 if [a for a in achados_dicts if a.get("severidade_key") == "CRITICO"]  else 0,
        1 if [a for a in achados_dicts if a.get("severidade_key") == "ALTO"]     else 0,
        1 if [a for a in achados_dicts if a.get("severidade_key") in ("MEDIO","ATENCAO")] else 0,
        1 if [a for a in achados_dicts if a.get("severidade_key") == "CONFORME"] else 0,
    ])
    total_pages = 2 + n_pag_achados + 1

    return {
        "contribuinte":       contrib_dict,
        "periodo":            {"inicio": periodo.inicio, "fim": periodo.fim},
        "resumo":             resumo_dict,
        "achados":            achados_dicts,
        "planilha_vendas":    _planilha_to_dicts(planilha_vendas),
        "planilha_remessas":  _planilha_to_dicts(planilha_remessas),
        "planilha_compras":   _planilha_to_dicts(planilha_compras),
        "recomendacoes":      recs,
        "sev_key":            sev_key,
        "sev_label":          sev_label,
        "n_achados":          len(achados_dicts),
        "n_criticos":         _cnt("CRITICO"),
        "n_altos":            _cnt("ALTO"),
        "n_medios":           _cnt("MEDIO"),
        "n_atencao":          _cnt("ATENCAO"),
        "n_conformes":        _cnt("CONFORME"),
        "hash_doc":           hash_doc,
        "total_pages":        total_pages,
    }


def gerar_laudo_v250(
    notas: list,  # list[NFA] (nfa-repo) ou list[NotaFiscal] (orgaudi_v240)
    cliente_nome: str,
    cliente_cpf: str,
    saida: Path,
    municipio: str = "Formoso",
    estado: str = "GO",
    contribuinte: Optional[Contribuinte] = None,
    periodo: Optional[Periodo] = None,
) -> None:
    """
    Gera o laudo OrgAudi v2.5.0 (HTML/CSS via Chrome headless).

    Interface compatível com gerar_laudo_orgaudi() do v240.

    Parâmetros
    ----------
    notas         : list[NFA] do nfa-repo OU list[NotaFiscal] do orgaudi_v240
    cliente_nome  : nome completo do contribuinte
    cliente_cpf   : CPF (11 dígitos, sem formatação ou com pontuação)
    saida         : caminho para o PDF de saída
    municipio     : município do contribuinte
    estado        : UF do contribuinte
    contribuinte  : Contribuinte pré-construído (opcional)
    periodo       : Periodo pré-definido (opcional)
    """
    from datetime import date

    saida = Path(saida)

    # ── Converter NFA → NotaFiscal se necessário ────────────────────────────
    # O adapter já tem toda a lógica de conversão; reutilizamos.
    from .adapter import _converter_nota, _normalizar_doc, _fallback_cpf
    import re

    cpf_limpo = re.sub(r"\D", "", str(cliente_cpf))

    notas_convertidas: list[NotaFiscal] = []
    for n in notas:
        if isinstance(n, NotaFiscal):
            notas_convertidas.append(n)
        else:
            try:
                notas_convertidas.append(_converter_nota(n))
            except Exception as e:
                logger.debug("Conversão NFA falhou: %s", e)

    if not notas_convertidas:
        logger.warning("Nenhuma nota convertida para %s", cliente_nome)
        return

    # Resolve CPF definitivo
    cpf_final = _fallback_cpf(cpf_limpo, notas_convertidas)

    if contribuinte is None:
        contribuinte = Contribuinte(
            nome=cliente_nome,
            cpf=cpf_final,
            municipio=municipio,
            estado=estado,
        )

    if periodo is None:
        datas = [n.data for n in notas_convertidas if n.data]
        inicio = min(datas) if datas else date(2025, 1, 1)
        fim    = max(datas) if datas else date(2025, 12, 31)
        periodo = Periodo(inicio=inicio, fim=fim)

    logger.info("Gerando laudo v250: %s → %s", cliente_nome, saida.name)

    ctx = _preparar_ctx(notas_convertidas, contribuinte, periodo)
    html = construir_html(ctx)
    html_para_pdf(html, saida)

    logger.info("Laudo v250 gerado: %s (%.1f KB)", saida.name, saida.stat().st_size / 1024)
