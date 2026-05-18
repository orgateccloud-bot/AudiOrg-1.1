#!/usr/bin/env python3
"""
Script para executar auditoria completa sobre PDFs de Entradas e Saídas.
Gera relatório em PDF como saída.

Uso:
    python executar_auditoria_pdfs.py

Entrada: ./input_pdfs/*.pdf
Saída: ./output_relatorios/DEUSDETE_AUDITORIA_2025.pdf
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s"
)
logger = logging.getLogger("auditoria_executor")

# Importar módulos do OrgAudi
from nfa_extractor.domain.extractor import extrair_notas, NFA, resumo_geral
from nfa_extractor.application.agents_engine import rodar_auditoria_completa
from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json


def listar_pdfs_entrada() -> List[Path]:
    """Lista todos os PDFs no diretório de entrada."""
    input_dir = Path("./input_pdfs")
    if not input_dir.exists():
        logger.error(f"Diretório {input_dir} não existe!")
        return []

    pdfs = list(input_dir.glob("*.pdf"))
    logger.info(f"Encontrados {len(pdfs)} PDFs para auditoria")
    for pdf in pdfs:
        logger.info(f"  - {pdf.name}")
    return pdfs


def extrair_todas_notas(pdfs: List[Path]) -> tuple[List[NFA], str]:
    """Extrai todas as notas fiscais dos PDFs.

    Returns:
        (lista de NFAs, nome do contribuinte extraído)
    """
    todas_notas: List[NFA] = []
    nome_contribuinte = "DEUSDETE"  # Default, será atualizado se encontrado

    for pdf_path in pdfs:
        logger.info(f"Extraindo notas de {pdf_path.name}...")
        try:
            notas = extrair_notas(str(pdf_path))
            todas_notas.extend(notas)
            logger.info(f"  Extraídas {len(notas)} notas de {pdf_path.name}")

            # Tentar extrair nome do contribuinte
            if notas and hasattr(notas[0], 'emitente_nome'):
                nome_contribuinte = notas[0].emitente_nome
        except Exception as e:
            logger.error(f"Erro ao extrair de {pdf_path.name}: {e}")
            continue

    logger.info(f"Total de notas extraídas: {len(todas_notas)}")
    return todas_notas, nome_contribuinte


def gerar_relatorio_auditoria(
    estado_auditoria: dict,
    notas: List[NFA],
    pdfs_origem: List[Path],
    output_dir: Path,
    nome_contribuinte: str
) -> Path:
    """Gera relatório em PDF com os resultados da auditoria.

    Args:
        estado_auditoria: Estado final do pipeline (Sigma/Gama/Auditor)
        notas: Lista de notas auditadas (para extrair estrutura)
        pdfs_origem: PDFs que foram auditados
        output_dir: Diretório para salvar o PDF
        nome_contribuinte: Nome do contribuinte

    Returns:
        Caminho do PDF gerado
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.pdf"

    logger.info(f"Gerando relatório em {output_path}...")

    # Construir dados no formato esperado por gerar_laudo_de_json
    # Extrair informações do primeiro NFA se disponível
    primeiro_nfa = notas[0] if notas else None

    def extrair_atributo_safe(obj, attr, default=None):
        """Extrair atributo com fallback seguro."""
        try:
            return getattr(obj, attr, default)
        except:
            return default

    dados_laudo = {
        "contribuinte": {
            "nome": nome_contribuinte,
            "cpf": extrair_atributo_safe(primeiro_nfa, 'emitente_cpf', '00000000000'),
            "ie": extrair_atributo_safe(primeiro_nfa, 'emitente_ie', ''),
            "municipio": extrair_atributo_safe(primeiro_nfa, 'emitente_municipio', 'São Paulo')
        },
        "periodo": {
            "inicio": "2025-01-01",
            "fim": "2025-12-31"
        },
        "notas": [
            {
                "numero": extrair_atributo_safe(n, 'numero', str(i)),
                "serie": extrair_atributo_safe(n, 'serie', '1'),
                "data": extrair_atributo_safe(n, 'data_emissao', '2025-01-01'),
                "destinatario": extrair_atributo_safe(n, 'destinatario_nome', 'Não especificado'),
                "produto": extrair_atributo_safe(n, 'produto_descricao', 'Serviço'),
                "quantidade": extrair_atributo_safe(n, 'quantidade', 1),
                "valor_unitario": extrair_atributo_safe(n, 'valor_unitario', 0),
                "valor_total": extrair_atributo_safe(n, 'valor_total', 0),
            }
            for i, n in enumerate(notas, 1)
        ]
    }

    try:
        # Gerar PDF usando gerar_laudo_de_json
        resultado = gerar_laudo_de_json(
            dados=dados_laudo,
            caminho_saida=str(output_path),
            strict_cpf=False  # Não falhar se CPF for inválido
        )

        logger.info(f"Relatório gerado com sucesso!")
        logger.info(f"  PDF: {output_path}")
        if "resumo_executivo" in resultado:
            logger.info(f"  Resumo Executivo: {resultado.get('resumo_executivo', '')[:100]}...")

    except Exception as e:
        logger.warning(f"Erro ao gerar PDF: {e}")
        logger.info("Salvando relatório em JSON como fallback...")

        # Fallback: salvar como JSON
        json_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            # Adicionar análises do pipeline
            dados_laudo["analise_sigma"] = estado_auditoria.get("analise_sigma", "")
            dados_laudo["analise_gama"] = estado_auditoria.get("analise_gama", "")
            dados_laudo["veredito_final"] = estado_auditoria.get("veredito_final", "")
            json.dump(dados_laudo, f, indent=2, ensure_ascii=False)
        logger.info(f"Relatório JSON salvo em: {json_path}")
        return json_path

    return output_path


def main():
    """Função principal."""
    logger.info("=" * 70)
    logger.info("INICIANDO AUDITORIA FISCAL — DEUSDETE 2025")
    logger.info("=" * 70)

    # 1. Listar e validar PDFs
    pdfs = listar_pdfs_entrada()
    if not pdfs:
        logger.error("Nenhum PDF encontrado para auditoria!")
        return 1

    # 2. Extrair notas dos PDFs
    logger.info("\n[FASE 1] Extração de Notas Fiscais")
    notas, nome_contribuinte = extrair_todas_notas(pdfs)

    if not notas:
        logger.error("Nenhuma nota fiscal foi extraída!")
        return 1

    # Gerar resumo
    logger.info("\nResumo das notas extraídas:")
    resumo = resumo_geral(notas, nome_contribuinte)
    logger.info(f"  Total de notas: {resumo['total_notas']}")
    logger.info(f"  Valor total: R$ {resumo['total_valor']:,.2f}")
    if 'total_cabecas' in resumo:
        logger.info(f"  Total de cabeças: {resumo.get('total_cabecas', 0):.1f}")

    # 3. Executar auditoria completa (Sigma → Gama → Auditor)
    logger.info("\n[FASE 2] Auditoria Completa (Sigma/Gama/Auditor)")
    logger.info("Aguarde... processando análise quantitativa, jurídica e final...")

    try:
        estado_auditoria = rodar_auditoria_completa(
            notas=notas,
            nome_contribuinte=nome_contribuinte,
            contexto_quant={
                "risk_score": 0.5,  # Será calculado pela engine se houver
                "fraud_level": "NONE"
            }
        )
        logger.info("Auditoria concluída com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao executar auditoria: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 4. Gerar relatório em PDF
    logger.info("\n[FASE 3] Geração de Relatório PDF")
    output_dir = Path("./output_relatorios")

    relatorio_path = gerar_relatorio_auditoria(
        estado_auditoria=estado_auditoria,
        notas=notas,
        pdfs_origem=pdfs,
        output_dir=output_dir,
        nome_contribuinte=nome_contribuinte
    )

    # 5. Resumo final
    logger.info("\n" + "=" * 70)
    logger.info("AUDITORIA CONCLUÍDA COM SUCESSO!")
    logger.info("=" * 70)
    logger.info(f"Relatório salvo em: {relatorio_path}")
    logger.info("\nVeredito Final:")
    veredito = estado_auditoria.get("veredito_final", "N/A")
    if veredito:
        logger.info(veredito[:500] + ("..." if len(veredito) > 500 else ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())
