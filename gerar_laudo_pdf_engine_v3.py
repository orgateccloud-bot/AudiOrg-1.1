#!/usr/bin/env python3
"""
Gera PDF v3 usando pdf_engine/orgaudi.
Correções aplicadas:
  1. Agrupamento multi-produto (notas únicas por número)
  2. CFOP 1.914 → COMPRA (F6)
  3. CFOP 5.914 verifica posição do contribuinte → REMESSA ou COMPRA
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json


def limpar_cpf(cpf: str) -> str:
    """Remove formatação do CPF/CNPJ."""
    return cpf.replace(".", "").replace("-", "").replace("/", "")


def determinar_natureza(cfop: str, remetente_cpf: str, destinatario_cpf: str,
                        cpf_contrib: str) -> str:
    """
    Classifica a natureza da NFA segundo posição do contribuinte e CFOP.

    Regra 1 OrgAudi:
      REMETENTE + 5.101          → VENDA   (F1 Receita)
      REMETENTE + 5.914 / 5.116  → REMESSA (F2 Trânsito)
      DESTINATÁRIO + 5.101       → COMPRA  (F6 Despesa)
      DESTINATÁRIO + 5.914       → COMPRA  (entrada de remessa recebida)
      DESTINATÁRIO + 1.914/2.914 → COMPRA  (F6)
    """
    cpf_rem  = limpar_cpf(remetente_cpf)
    cpf_dest = limpar_cpf(destinatario_cpf)

    eh_remetente   = (cpf_rem  == cpf_contrib)
    eh_destinatario = (cpf_dest == cpf_contrib)

    if eh_remetente:
        if cfop in ('5.101', '6.101'):
            return 'VENDA'
        if cfop in ('5.914', '5.116', '6.914'):
            return 'REMESSA'
        return 'VENDA'  # fallback saída

    if eh_destinatario:
        # Qualquer entrada (compra, remessa recebida) → COMPRA para fins F6
        return 'COMPRA'

    return 'VENDA'  # não identificado, mantém saída


def agrupar_por_numero(notas: list[dict], cpf_contrib: str) -> list[dict]:
    """
    Agrupa linhas multi-produto da mesma NFA em uma única nota.
    Soma quantidade e valor_total; usa natureza, CPFs e data da primeira linha.

    Correção especial (CFOP 5.914 rem==dest==contribuinte):
      O GIEF/Tocantins registra remessas para leilão com o próprio contribuinte
      como destinatário. O pdf_engine classificaria como TRANSFERÊNCIA (neutro).
      Para preservar o F2 (trânsito), zeramos o destinatario_cpf nesse caso,
      forçando a classificação REMETENTE + REMESSA → CategoriaContabil.TRANSITO.
    """
    grupos: dict[str, dict] = {}

    for nfa in notas:
        num  = nfa['numero']
        cfop = nfa.get('cfop', '')
        cpf_rem  = limpar_cpf(nfa.get('remetente_cpf', ''))
        cpf_dest = limpar_cpf(nfa.get('destinatario_cpf', ''))

        # ── Correção: remessa para leilão registrada com rem==dest==contrib ──
        eh_remessa_leilao = (
            cfop in ('5.914', '5.116')
            and cpf_rem == cpf_contrib
            and cpf_dest == cpf_contrib
        )

        # CPF destinatário efetivo: esvaziar nas remessas para leilão
        dest_cpf_efetivo  = '' if eh_remessa_leilao else nfa.get('destinatario_cpf', '')
        dest_nome_efetivo = nfa.get('destinatario_nome', '')

        natureza = determinar_natureza(
            cfop, nfa.get('remetente_cpf', ''), dest_cpf_efetivo, cpf_contrib
        )

        if num not in grupos:
            grupos[num] = {
                'numero': num,
                'data':   nfa['data'],
                'natureza': natureza,
                'cfop':   cfop,
                'remetente_cpf':     nfa.get('remetente_cpf', ''),
                'remetente_nome':    nfa.get('remetente_nome', ''),
                'destinatario_cpf':  dest_cpf_efetivo,
                'destinatario_nome': dest_nome_efetivo,
                'produto':    nfa.get('produto', ''),
                'quantidade': 0.0,
                'valor_total': 0.0,
            }

        grupos[num]['quantidade']  += float(nfa.get('quantidade', 0))
        grupos[num]['valor_total'] += float(nfa.get('valor_total', 0))

    return list(grupos.values())


def converter_para_laudo(json_path: str, pdf_path: str) -> bool:
    """Converte JSON v2 para formato pdf_engine com correções de qualidade."""

    logger.info(f"Carregando JSON: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        audit_data = json.load(f)

    contribuinte = audit_data['contribuinte']
    notas_raw    = audit_data['notas']

    cpf_contrib = limpar_cpf(contribuinte['cpf_cnpj'])

    # ── CORREÇÃO 1: Agrupar multi-produto por número de NFA ──────────────────
    notas_unicas = agrupar_por_numero(notas_raw, cpf_contrib)

    logger.info(f"Linhas brutas: {len(notas_raw)} → Notas únicas: {len(notas_unicas)}")

    # ── Estatísticas de natureza ──────────────────────────────────────────────
    nat_count: dict[str, int] = defaultdict(int)
    for n in notas_unicas:
        nat_count[n['natureza']] += 1

    logger.info(f"Distribuição de naturezas: {dict(nat_count)}")

    # ── Converter para formato pdf_engine ─────────────────────────────────────
    notas_convertidas = []
    for nfa in notas_unicas:
        # Data DD/MM/YYYY → YYYY-MM-DD
        partes = nfa['data'].split('/')
        data_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"

        notas_convertidas.append({
            "numero":          str(nfa['numero']),
            "data":            data_iso,
            "natureza":        nfa['natureza'],
            "valor":           Decimal(str(round(nfa['valor_total'], 2))),
            "cabecas":         int(round(nfa['quantidade'])),
            "remetente_cpf":   nfa['remetente_cpf'],
            "remetente_nome":  nfa['remetente_nome'],
            "destinatario_cpf":   nfa['destinatario_cpf'],
            "destinatario_nome":  nfa['destinatario_nome'],
        })

    # ── Montar payload para pdf_engine ────────────────────────────────────────
    dados_laudo = {
        "contribuinte": {
            "nome":     contribuinte['nome'],
            "cpf":      cpf_contrib,
            "ie":       "",
            "municipio": "Tocantins",
            "estado":   "TO",
            "eh_pj":    len(cpf_contrib) == 14,
            "eh_segurado_especial": False
        },
        "periodo": {
            "inicio":         "2025-01-01",
            "fim":            "2025-12-31",
            "data_auditoria": datetime.now().strftime("%Y-%m-%d")
        },
        "notas": notas_convertidas
    }

    logger.info(f"Gerando PDF: {pdf_path}")

    try:
        resultado = gerar_laudo_de_json(
            dados=dados_laudo,
            caminho_saida=pdf_path,
            strict_cpf=False
        )

        kpis   = resultado.get('kpis', {})
        achados = resultado.get('achados', [])

        logger.info(f"\n✓ PDF gerado  |  Hash: {resultado.get('hash', 'N/A')}")
        logger.info(f"\n  KPIs:")
        logger.info(f"    F1 Receita Imediata : R$ {kpis.get('F1_receita_imediata', 0):>15,.2f}")
        logger.info(f"    F2 Trânsito         : R$ {kpis.get('F2_transito', 0):>15,.2f}")
        logger.info(f"    F4 Receita Bruta    : R$ {kpis.get('F4_receita_bruta', 0):>15,.2f}")
        logger.info(f"    F6 Despesa          : R$ {kpis.get('F6_despesa', 0):>15,.2f}")
        logger.info(f"    F5 Resultado Rural  : R$ {kpis.get('F5_resultado_rural', 0):>15,.2f}")
        logger.info(f"    Funrural            : R$ {kpis.get('funrural', 0):>15,.2f}")
        logger.info(f"    IRPF Estimado       : R$ {kpis.get('irpf_estimado', 0):>15,.2f}")
        logger.info(f"    Qtd Vendas          : {kpis.get('qtd_vendas', 0)}")
        logger.info(f"    Qtd Compras         : {kpis.get('qtd_compras', 0)}")
        logger.info(f"    Qtd Remessas        : {kpis.get('qtd_remessas', 0)}")

        if achados:
            logger.info(f"\n  Achados ({len(achados)}):")
            for a in achados:
                logger.info(f"    • {a['codigo']}: {a['titulo']} [{a['severidade']}]")

    except Exception as e:
        logger.error(f"✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    logger.info("=" * 70)
    logger.info("LAUDO OrgAudi v3 — com correções de qualidade")
    logger.info("=" * 70 + "\n")

    output_dir = Path("./output_relatorios")

    jsons_v2 = sorted(output_dir.glob("*V2*.json"), key=lambda p: p.stat().st_mtime)
    if not jsons_v2:
        logger.error("Nenhum JSON V2 encontrado. Execute auditoria_parser_v2.py primeiro!")
        return 1

    json_path = jsons_v2[-1]
    pdf_path  = json_path.parent / f"{json_path.stem}_v3_LAUDO.pdf"

    logger.info(f"JSON: {json_path.name}")
    logger.info(f"PDF:  {pdf_path.name}\n")

    if converter_para_laudo(str(json_path), str(pdf_path)):
        logger.info(f"\n✅ Laudo salvo em: {pdf_path}")
        return 0
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
