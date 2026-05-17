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


def _etapas_recomendadas(achados: list[dict], resumo_dict: dict) -> list[dict]:
    """Gera 3 etapas de recomendações (30/60/90 dias) — formato MODELO."""
    tem_critico = any(a.get("severidade_key") == "CRITICO" for a in achados)
    tem_alto    = any(a.get("severidade_key") == "ALTO" for a in achados)

    itens1 = []
    if tem_critico:
        itens1 += [
            "Solicitar documentação primária dos achados críticos: GTAs (AGRODEFESA-GO), "
            "extratos bancários e ACTs dos leiloeiros.",
            "Cruzar com Receita Federal (CAEPF dos PFs recorrentes), SiCAR (capacidade "
            "do imóvel) e JUCEG (vínculos societários).",
        ]
    if tem_alto:
        itens1.append(
            "Verificar CAEPF dos destinatários recorrentes (3+ aquisições no período)."
        )
    if not itens1:
        itens1 = ["Revisar documentação primária dos achados identificados."]

    itens2 = [
        "Reconstituir o LCDPR 2025 separando rigorosamente receita de trânsito.",
        "Apurar o IRPF Rural 2026 considerando apenas as receitas efetivamente realizadas.",
        f"Conferir Funrural recolhido contra a estimativa de "
        f"{resumo_dict.get('funrural_fmt', '—')} deste relatório.",
    ]

    itens3 = [
        "Implantar segregação de fluxos: rotina para vendas a PF (checagem CAEPF) e "
        "cobrança formal das notas de venda do leiloeiro.",
        "Adequar à Reforma Tributária (LC 214/2025): a partir de 2027, CBS substitui "
        "PIS/COFINS na cadeia agro. Atualizar NFA-e/NF-e conforme NT 2025.002 RTC.",
    ]

    return [
        {"titulo": "Aprofundar achados críticos", "prazo": "30 dias", "itens": itens1},
        {"titulo": "Conformidade fiscal",          "prazo": "60 dias", "itens": itens2},
        {"titulo": "Mitigação prospectiva",        "prazo": "90 dias", "itens": itens3},
    ]


def _calcular_extras(notas: list[NotaFiscal], contribuinte: Contribuinte, resumo) -> dict:
    """Calcula campos adicionais para a síntese quantitativa da capa."""
    from .domain import NaturezaNota
    import re

    cpf = re.sub(r"\D", "", contribuinte.cpf)

    volume_total = sum(n.valor for n in notas)
    cabecas_total = sum(n.cabecas for n in notas)

    dest_unicos = {
        re.sub(r"\D", "", n.destinatario_cpf)
        for n in notas
        if re.sub(r"\D", "", n.remetente_cpf) == cpf
        and n.natureza == NaturezaNota.VENDA
        and n.destinatario_cpf
        and re.sub(r"\D", "", n.destinatario_cpf) != cpf
    }

    if volume_total > 0:
        receita_pct = float(resumo.F1_receita_imediata / volume_total * 100)
        remessas_pct = float(resumo.F2_transito / volume_total * 100)
    else:
        receita_pct = remessas_pct = 0.0

    return {
        "volume_bruto_fmt":     fmt_brl(volume_total),
        "cabecas_total":        f"{cabecas_total:,}".replace(",", "."),
        "destinatarios_unicos": len(dest_unicos),
        "receita_pct":          f"{receita_pct:.1f}%".replace(".", ","),
        "remessas_pct":         f"{remessas_pct:.1f}%".replace(".", ","),
    }


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
    extras = _calcular_extras(notas, contribuinte, resumo)

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
        "periodo_str":          f"{fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}",
        "receita_fmt":          fmt_brl(resumo.F1_receita_imediata),
        "remessas_fmt":         fmt_brl(resumo.F2_transito),
        "compras_fmt":          fmt_brl(resumo.F6_despesa),
        "funrural_fmt":         fmt_brl(resumo.funrural),
        "aliq_funrural":        f"{float(resumo.aliquota_funrural) * 100:.2f}%".replace(".", ","),
        "notas_vendas":         resumo.qtd_vendas,
        "notas_remessas":       resumo.qtd_remessas,
        "notas_compras":        getattr(resumo, "qtd_compras", 0),
        "valor_bruto_saidas":   str(resumo.F4_receita_bruta),
        "total_notas":          len(notas),
        "data_auditoria":       fmt_data(periodo.data_auditoria),
        **extras,
    }

    # ── Dados do contribuinte para o template ────────────────────────────────
    contrib_dict = {
        "nome":        contribuinte.nome,
        "cpf":         contribuinte.cpf,
        "cpf_fmt":     _fmt_cpf(contribuinte.cpf),
        "ie":          contribuinte.ie or "—",
        "municipio":   getattr(contribuinte, "municipio", "Formoso"),
        "estado":      getattr(contribuinte, "estado", "GO"),
        "periodo_str": f"{fmt_data(periodo.inicio)} a {fmt_data(periodo.fim)}",
    }

    # Etapas de recomendações (3 etapas: 30/60/90 dias)
    etapas = _etapas_recomendadas(achados_dicts, resumo_dict)

    # Total de páginas: 1 capa + achados + 1 recomendações + 1 fórmulas + 1 assinatura
    n_pag_achados = sum([
        1 if [a for a in achados_dicts if a.get("severidade_key") == "CRITICO"]  else 0,
        1 if [a for a in achados_dicts if a.get("severidade_key") == "ALTO"]     else 0,
        1 if [a for a in achados_dicts if a.get("severidade_key") in ("MEDIO","ATENCAO")] else 0,
        1 if [a for a in achados_dicts if a.get("severidade_key") == "CONFORME"] else 0,
    ])
    total_pages = 1 + n_pag_achados + 1 + 1 + 1  # capa + achados + recomend. + fórmulas + assinatura

    return {
        "contribuinte":       contrib_dict,
        "periodo":            {"inicio": periodo.inicio, "fim": periodo.fim},
        "resumo":             resumo_dict,
        "achados":            achados_dicts,
        "planilha_vendas":    _planilha_to_dicts(planilha_vendas),
        "planilha_remessas":  _planilha_to_dicts(planilha_remessas),
        "planilha_compras":   _planilha_to_dicts(planilha_compras),
        "etapas":             etapas,
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
