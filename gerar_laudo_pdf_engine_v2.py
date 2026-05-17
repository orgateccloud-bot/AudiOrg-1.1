#!/usr/bin/env python3
"""
Gera PDF profissional v2 usando pdf_engine/orgaudi com CPFs estruturados.
Permite ativar todos os testes forenses (T-01 a T-08) e tipologias AN-XX.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json


def determinar_natureza(nfa: dict, cpf_contribuinte_limpo: str) -> str:
    """Determina natureza baseado em CFOP e posição do contribuinte."""

    cfop = nfa.get('cfop', '')
    rem_cpf = nfa.get('remetente_cpf', '').replace('.', '').replace('-', '').replace('/', '')
    dest_cpf = nfa.get('destinatario_cpf', '').replace('.', '').replace('-', '').replace('/', '')

    # CFOP define natureza:
    # 5.101 = Venda de produção (saída)
    # 5.914 = Remessa para industrialização/leilão
    # 1.101 = Compra
    # 2.101 = Compra interestadual

    if cfop == '5.914':
        return 'REMESSA'
    elif cfop in ('5.101', '6.101'):
        # Venda do remetente
        return 'VENDA'
    elif cfop in ('1.101', '2.101'):
        return 'COMPRA'
    elif cfop == '5.116':
        return 'LEILAO'
    else:
        return 'VENDA'  # default


def converter_para_laudo(json_path: str, pdf_path: str):
    """Converte JSON v2 (com CPFs) para formato pdf_engine."""

    logger.info(f"Carregando JSON: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        audit_data = json.load(f)

    contribuinte = audit_data['contribuinte']
    notas_audit = audit_data['notas']

    cpf_contribuinte = contribuinte['cpf_cnpj'].replace(".", "").replace("/", "").replace("-", "")

    # Converter notas
    notas_convertidas = []

    for nfa in notas_audit:
        natureza = determinar_natureza(nfa, cpf_contribuinte)

        # Converter data DD/MM/YYYY → YYYY-MM-DD
        data_partes = nfa['data'].split('/')
        data_convertida = f"{data_partes[2]}-{data_partes[1]}-{data_partes[0]}"

        nfa_convertida = {
            "numero": str(nfa['numero']),
            "data": data_convertida,
            "natureza": natureza,
            "valor": Decimal(str(nfa['valor_total'])),
            "cabecas": int(round(nfa['quantidade'])),
            "remetente_cpf": nfa.get('remetente_cpf', ''),
            "remetente_nome": nfa.get('remetente_nome', ''),
            "destinatario_cpf": nfa.get('destinatario_cpf', ''),
            "destinatario_nome": nfa.get('destinatario_nome', ''),
        }
        notas_convertidas.append(nfa_convertida)

    # Preparar dados
    dados_laudo = {
        "contribuinte": {
            "nome": contribuinte['nome'],
            "cpf": cpf_contribuinte,
            "ie": "",
            "municipio": "Tocantins",
            "estado": "TO",
            "eh_pj": False,  # 11 dígitos = PF
            "eh_segurado_especial": False
        },
        "periodo": {
            "inicio": "2025-01-01",
            "fim": "2025-12-31",
            "data_auditoria": datetime.now().strftime("%Y-%m-%d")
        },
        "notas": notas_convertidas
    }

    logger.info(f"Convertendo {len(notas_convertidas)} notas para formato OrgAudi...")
    logger.info(f"Gerando PDF: {pdf_path}")

    # Estatísticas das naturezas
    nat_count = {}
    for n in notas_convertidas:
        nat_count[n['natureza']] = nat_count.get(n['natureza'], 0) + 1
    logger.info(f"Distribuição de naturezas: {nat_count}")

    try:
        resultado = gerar_laudo_de_json(
            dados=dados_laudo,
            caminho_saida=pdf_path,
            strict_cpf=False
        )

        logger.info(f"\n✓ PDF gerado com sucesso!")
        logger.info(f"  Hash: {resultado.get('hash', 'N/A')}")
        logger.info(f"\n  KPIs:")
        kpis = resultado.get('kpis', {})
        logger.info(f"    • F1 Receita Imediata: R$ {kpis.get('F1_receita_imediata', 0):,.2f}")
        logger.info(f"    • F2 Trânsito:          R$ {kpis.get('F2_transito', 0):,.2f}")
        logger.info(f"    • F4 Receita Bruta:     R$ {kpis.get('F4_receita_bruta', 0):,.2f}")
        logger.info(f"    • F5 Resultado Rural:   R$ {kpis.get('F5_resultado_rural', 0):,.2f}")
        logger.info(f"    • F6 Despesa:           R$ {kpis.get('F6_despesa', 0):,.2f}")
        logger.info(f"    • Funrural:             R$ {kpis.get('funrural', 0):,.2f}")
        logger.info(f"    • IRPF Estimado:        R$ {kpis.get('irpf_estimado', 0):,.2f}")
        logger.info(f"    • Quantidade Vendas:    {kpis.get('qtd_vendas', 0)}")
        logger.info(f"    • Quantidade Compras:   {kpis.get('qtd_compras', 0)}")
        logger.info(f"    • Quantidade Remessas:  {kpis.get('qtd_remessas', 0)}")

        achados = resultado.get('achados', [])
        if achados:
            logger.info(f"\n  Achados Detectados: {len(achados)}")
            for ach in achados:
                logger.info(f"    • {ach['codigo']}: {ach['titulo']} ({ach['severidade']})")

    except Exception as e:
        logger.error(f"✗ Erro ao gerar PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    logger.info("=" * 70)
    logger.info("GERANDO LAUDO PDF v2 (com CPFs estruturados)")
    logger.info("=" * 70 + "\n")

    output_dir = Path("./output_relatorios")

    # JSON V2 mais recente
    jsons_v2 = sorted(output_dir.glob("*V2*.json"), key=lambda p: p.stat().st_mtime)
    if not jsons_v2:
        logger.error("Nenhum JSON V2 encontrado. Execute auditoria_parser_v2.py primeiro!")
        return 1

    json_path = jsons_v2[-1]
    pdf_path = json_path.parent / f"{json_path.stem}_LAUDO.pdf"

    logger.info(f"JSON: {json_path.name}")
    logger.info(f"PDF:  {pdf_path.name}\n")

    if converter_para_laudo(str(json_path), str(pdf_path)):
        logger.info(f"\n✅ Laudo OrgAudi v2 salvo em:")
        logger.info(f"   {pdf_path}")
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
