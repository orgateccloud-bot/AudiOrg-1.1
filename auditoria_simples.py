#!/usr/bin/env python3
"""
Script simplificado para executar auditoria sobre PDFs de Entradas/Saídas.
Foco: extrair notas → executar auditoria (Sigma/Gama/Auditor) → gerar relatório JSON/PDF.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger("auditoria")

from nfa_extractor.domain.extractor import extrair_notas, resumo_geral
from nfa_extractor.application.agents_engine import rodar_auditoria_completa


def main():
    logger.info("=" * 70)
    logger.info("AUDITORIA FISCAL — DEUSDETE 2025")
    logger.info("=" * 70)

    # 1. Listar PDFs
    input_dir = Path("./input_pdfs")
    pdfs = list(input_dir.glob("*.pdf"))
    logger.info(f"Encontrados {len(pdfs)} PDFs")

    if not pdfs:
        logger.error("Nenhum PDF encontrado!")
        return 1

    # 2. Extrair notas
    logger.info("\n[FASE 1] Extração de Notas Fiscais")
    todas_notas = []
    nome_contribuinte = "DEUSDETE"

    for pdf_path in pdfs:
        logger.info(f"  Extraindo de {pdf_path.name}...")
        try:
            # extrair_notas retorna tupla: (List[NFA], nome_produtor, cpf_produtor)
            notas, nome, cpf = extrair_notas(str(pdf_path))
            if notas:
                todas_notas.extend(notas)
                nome_contribuinte = nome or nome_contribuinte
                logger.info(f"    ✓ Extraídas {len(notas)} notas")
            else:
                logger.warning(f"    ⚠ Nenhuma nota extraída deste PDF")
        except Exception as e:
            logger.error(f"    ✗ Erro: {e}")

    logger.info(f"Total de notas: {len(todas_notas)}")

    if not todas_notas:
        logger.error("Nenhuma nota foi extraída!")
        return 1

    # 3. Preparar dados básicos
    try:
        resumo = resumo_geral(todas_notas, nome_contribuinte)
        logger.info(f"\nResumo:")
        logger.info(f"  Total de notas: {resumo.get('total_notas', 0)}")
        logger.info(f"  Valor total: R$ {resumo.get('total_valor', 0):,.2f}")
    except Exception as e:
        logger.warning(f"Erro ao gerar resumo: {e}")

    # 4. Executar auditoria completa
    logger.info("\n[FASE 2] Auditoria Completa (Sigma/Gama/Auditor)")
    logger.info("Processando análise quantitativa, jurídica e final...")

    try:
        estado = rodar_auditoria_completa(
            notas=todas_notas,
            nome_contribuinte=nome_contribuinte,
            contexto_quant={"risk_score": 0.5, "fraud_level": "NONE"}
        )
        logger.info("✓ Auditoria concluída!")
    except Exception as e:
        logger.error(f"Erro na auditoria: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 5. Salvar relatório JSON
    logger.info("\n[FASE 3] Geração de Relatório")
    output_dir = Path("./output_relatorios")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    relatorio_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.json"

    relatorio = {
        "titulo": "Relatório de Auditoria Fiscal",
        "contribuinte": nome_contribuinte,
        "data_auditoria": datetime.now().isoformat(),
        "resumo": resumo if 'resumo' in locals() else {},
        "total_notas_processadas": len(todas_notas),
        "analise_sigma": estado.get("analise_sigma", ""),
        "analise_gama": estado.get("analise_gama", ""),
        "veredito_final": estado.get("veredito_final", ""),
        "historico": estado.get("historico", []),
    }

    with open(relatorio_path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)

    logger.info(f"\n✓ Relatório JSON salvo em: {relatorio_path}")

    # 6. Tentar gerar PDF a partir do JSON
    logger.info("\n[FASE 4] Geração de Relatório PDF")
    try:
        from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json

        dados_pdf = {
            "contribuinte": {
                "nome": nome_contribuinte,
                "cpf": "00000000000",
                "ie": "",
                "municipio": "São Paulo"
            },
            "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
            "notas": []  # Notas vazias por enquanto
        }

        pdf_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.pdf"
        resultado = gerar_laudo_de_json(
            dados=dados_pdf,
            caminho_saida=str(pdf_path),
            strict_cpf=False
        )
        logger.info(f"✓ Relatório PDF salvo em: {pdf_path}")

    except Exception as e:
        logger.warning(f"Não foi possível gerar PDF: {e}")

    # 7. Resumo final
    logger.info("\n" + "=" * 70)
    logger.info("AUDITORIA CONCLUÍDA COM SUCESSO!")
    logger.info("=" * 70)
    logger.info(f"Relatório: {relatorio_path}")

    if estado.get("veredito_final"):
        logger.info(f"\nVeredito:\n{estado['veredito_final'][:500]}...")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
