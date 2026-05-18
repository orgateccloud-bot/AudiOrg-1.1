#!/usr/bin/env python3
"""
Gera PDF profissional usando pdf_engine/orgaudi.
Converte dados de auditoria para formato LaudoOrgAudi.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json


def converter_para_laudo(json_path: str, pdf_path: str):
    """Converte JSON de auditoria para formato pdf_engine e gera PDF."""

    logger.info(f"Carregando JSON: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        audit_data = json.load(f)

    contribuinte = audit_data['contribuinte']
    resumo = audit_data['resumo']
    notas_audit = audit_data['notas']

    # Extrair CPF do contribuinte (será usado para preencher remetente_cpf ou destinatario_cpf)
    cpf_contribuinte = contribuinte['cpf_cnpj'].replace(".", "").replace("/", "").replace("-", "")

    # Converter notas para formato LaudoOrgAudi
    # Determinar natureza baseado no remetente/destinatário
    notas_convertidas = []

    for nfa in notas_audit:
        # Se DEUSDETE é o destinatário → é uma COMPRA/entrada
        # Se DEUSDETE é o remetente → é uma VENDA/saída

        eh_venda = (
            "DEUSDETE" in nfa.get('remetente', '').upper()
        )

        natureza = "VENDA" if eh_venda else "COMPRA"

        # Converter data de DD/MM/YYYY para YYYY-MM-DD
        data_partes = nfa['data'].split('/')
        data_convertida = f"{data_partes[2]}-{data_partes[1]}-{data_partes[0]}"

        # Preencher CPFs: usar CPF do contribuinte no campo apropriado
        if eh_venda:
            # DEUSDETE é remetente (venda)
            remetente_cpf = cpf_contribuinte
            destinatario_cpf = ""
        else:
            # DEUSDETE é destinatário (compra)
            remetente_cpf = ""
            destinatario_cpf = cpf_contribuinte

        nfa_convertida = {
            "numero": str(nfa['numero']),
            "data": data_convertida,
            "natureza": natureza,
            "valor": Decimal(str(nfa['valor_total'])),
            "cabecas": int(round(nfa['quantidade'])),
            "remetente_cpf": remetente_cpf,
            "remetente_nome": nfa.get('remetente', ''),
            "destinatario_cpf": destinatario_cpf,
            "destinatario_nome": nfa.get('destinatario', ''),
        }
        notas_convertidas.append(nfa_convertida)

    # Preparar dados para gerar_laudo_de_json
    dados_laudo = {
        "contribuinte": {
            "nome": contribuinte['nome'],
            "cpf": contribuinte['cpf_cnpj'].replace(".", "").replace("/", "").replace("-", ""),
            "ie": "",
            "municipio": "Tocantins",
            "estado": "TO",
            "eh_pj": True,  # CNPJ indica PJ
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

    # DEBUG: verificar estrutura dos dados
    logger.info(f"DEBUG - Primeira nota convertida: {notas_convertidas[0] if notas_convertidas else 'NENHUMA'}")
    logger.info(f"DEBUG - Total de notas em dados_laudo: {len(dados_laudo['notas'])}")

    try:
        resultado = gerar_laudo_de_json(
            dados=dados_laudo,
            caminho_saida=pdf_path,
            strict_cpf=False
        )

        logger.info(f"✓ PDF gerado com sucesso!")
        logger.info(f"  Hash: {resultado.get('hash', 'N/A')}")
        logger.info(f"\n  KPIs:")
        kpis = resultado.get('kpis', {})
        logger.info(f"    • Receita Imediata: R$ {kpis.get('F1_receita_imediata', 0):,.2f}")
        logger.info(f"    • Transito: R$ {kpis.get('F2_transito', 0):,.2f}")
        logger.info(f"    • Receita Bruta: R$ {kpis.get('F4_receita_bruta', 0):,.2f}")
        logger.info(f"    • Resultado Rural: R$ {kpis.get('F5_resultado_rural', 0):,.2f}")
        logger.info(f"    • Quantidade Vendas: {kpis.get('qtd_vendas', 0)}")
        logger.info(f"    • Quantidade Compras: {kpis.get('qtd_compras', 0)}")

        achados = resultado.get('achados', [])
        if achados:
            logger.info(f"\n  Achados Detectados: {len(achados)}")
            for ach in achados[:5]:  # Mostrar primeiros 5
                logger.info(f"    • {ach['codigo']}: {ach['titulo']} ({ach['severidade']})")

    except Exception as e:
        logger.error(f"✗ Erro ao gerar PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    logger.info("=" * 70)
    logger.info("GERANDO LAUDO PDF COM pdf_engine/orgaudi")
    logger.info("=" * 70 + "\n")

    output_dir = Path("./output_relatorios")

    # Encontrar JSON mais recente
    jsons = sorted(output_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not jsons:
        logger.error("Nenhum JSON encontrado em output_relatorios/")
        return 1

    json_path = jsons[-1]
    pdf_path = json_path.parent / f"{json_path.stem}_pdf-engine.pdf"

    logger.info(f"JSON: {json_path.name}")
    logger.info(f"PDF: {pdf_path.name}\n")

    if converter_para_laudo(str(json_path), str(pdf_path)):
        logger.info(f"\n✅ Laudo OrgAudi salvo em:")
        logger.info(f"   {pdf_path}")
        return 0
    else:
        logger.error("Falha ao gerar laudo")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
