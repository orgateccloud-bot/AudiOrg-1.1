#!/usr/bin/env python3
"""
Parser simples para NFAs — parse por índice de palavras.
"""

import json
import re
import pdfplumber
import logging
from pathlib import Path
from datetime import datetime
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("auditoria")


class NFA:
    def __init__(self, numero, data, remetente, destinatario, produto, qtd, vlr_unit, vlr_total):
        self.numero = numero
        self.data = data
        self.remetente = remetente
        self.destinatario = destinatario
        self.produto = produto
        self.quantidade = qtd
        self.valor_unitario = vlr_unit
        self.valor_total = vlr_total


def extrair_nfas(pdf_path: str) -> tuple[List[NFA], str, str]:
    """Extrai NFAs parsing as linhas por índice de palavras."""

    nfas = []
    nome_contribuinte = ""
    cpf_contribuinte = ""

    with pdfplumber.open(pdf_path) as pdf:
        texto = "\n".join([p.extract_text() or "" for p in pdf.pages])

    # Extrair CPF do contribuinte
    match_cpf = re.search(r"CNPJ/CPF:\s*([\d./-]+)", texto)
    if match_cpf:
        cpf_contribuinte = match_cpf.group(1).strip()

    # Processar linhas
    for line in texto.split('\n'):
        parts = line.split()

        # Validar: começa com número 7-8 dígitos
        if not parts or not re.match(r'^\d{7,8}$', parts[0]):
            continue

        try:
            # [0] número, [1] data, [2] cpf_rem, [3-6] nome_rem, [7] cfop,
            # [8] cpf_dest, [9-?] nome_dest, [...] produto, [...] qtd, vlr_unit, vlr_total

            numero = parts[0]
            data = parts[1]  # DD/MM/YYYY

            # CPF remetente (partes[2])
            # Nome remetente: procurar até encontrar CFOP (formato X.XXX)
            cfop_idx = None
            for i in range(3, min(len(parts), 15)):
                if re.match(r'\d\.\d{3}', parts[i]):
                    cfop_idx = i
                    break

            if not cfop_idx:
                continue

            nome_remetente = " ".join(parts[3:cfop_idx])
            cfop = parts[cfop_idx]

            # CPF destinatário
            cpf_dest = parts[cfop_idx + 1]

            # Nome destinatário: procurar até encontrar palavra que começa com "BOVINO"
            nome_dest_end = None
            for i in range(cfop_idx + 2, len(parts)):
                if parts[i].startswith("BOVINO") or parts[i].startswith("bovino"):
                    nome_dest_end = i
                    break

            if not nome_dest_end:
                continue

            nome_dest = " ".join(parts[cfop_idx + 2:nome_dest_end])

            # Produto: de "BOVINO" até encontrar número com vírgula (quantidade)
            produto_end = None
            for i in range(nome_dest_end, len(parts)):
                if re.match(r'[\d.,]+', parts[i]):  # Primeiro número = quantidade
                    produto_end = i
                    break

            if not produto_end or produto_end + 2 >= len(parts):
                continue

            produto = " ".join(parts[nome_dest_end:produto_end])

            # Quantidade, valor unitário, valor total (últimas 3 partes)
            def limpar_valor(s):
                s = str(s).replace(".", "").replace(",", ".")
                try:
                    return float(s)
                except:
                    return 0

            qtd = limpar_valor(parts[produto_end])
            vlr_unit = limpar_valor(parts[-2])
            vlr_total = limpar_valor(parts[-1])

            nfa = NFA(numero, data, nome_remetente, nome_dest, produto, qtd, vlr_unit, vlr_total)
            nfas.append(nfa)

            # Atualizar contribuinte se for destinatário (geralmente DEUSDETE)
            if "DEUSDETE" in nome_dest.upper():
                nome_contribuinte = nome_dest

        except Exception as e:
            logger.debug(f"Erro ao parsear: {e}")
            continue

    return nfas, nome_contribuinte or "DEUSDETE", cpf_contribuinte


def main():
    logger.info("=" * 70)
    logger.info("AUDITORIA FISCAL — DEUSDETE 2025")
    logger.info("=" * 70)

    input_dir = Path("./input_pdfs")
    output_dir = Path("./output_relatorios")
    output_dir.mkdir(exist_ok=True)

    pdfs = list(input_dir.glob("*.pdf"))
    logger.info(f"\nEncontrados {len(pdfs)} PDFs\n")

    # [FASE 1] Extração
    logger.info("[FASE 1] Extração de NFAs")
    todas_nfas = []
    nome_final = "DEUSDETE"
    cpf_final = ""

    for pdf_path in sorted(pdfs):
        logger.info(f"  Processando {pdf_path.name}...")
        nfas, nome, cpf = extrair_nfas(str(pdf_path))

        if nfas:
            todas_nfas.extend(nfas)
            nome_final = nome or nome_final
            cpf_final = cpf or cpf_final
            logger.info(f"    ✓ Extraídas {len(nfas)} NFAs")
        else:
            logger.warning(f"    ⚠ Nenhuma NFA extraída")

    if not todas_nfas:
        logger.error("Erro: Nenhuma NFA extraída!")
        return 1

    logger.info(f"\nTotal de NFAs: {len(todas_nfas)}")

    # [FASE 2] Resumo
    logger.info("\n[FASE 2] Resumo")

    total_valor = sum(n.valor_total for n in todas_nfas)
    total_qtd = sum(n.quantidade for n in todas_nfas)

    logger.info(f"  Contribuinte: {nome_final} ({cpf_final})")
    logger.info(f"  Total de notas: {len(todas_nfas)}")
    logger.info(f"  Quantidade: {total_qtd:.1f}")
    logger.info(f"  Valor total: R$ {total_valor:,.2f}")

    # Agrupar por remetente
    por_remetente = {}
    for nfa in todas_nfas:
        rem = nfa.remetente
        if rem not in por_remetente:
            por_remetente[rem] = {"notas": 0, "valor": 0}
        por_remetente[rem]["notas"] += 1
        por_remetente[rem]["valor"] += nfa.valor_total

    logger.info(f"\n  Top remetentes:")
    for rem, dados in sorted(por_remetente.items(), key=lambda x: x[1]["valor"], reverse=True)[:5]:
        logger.info(f"    {rem}: {dados['notas']} notas, R$ {dados['valor']:,.2f}")

    # [FASE 3] Salvar relatório JSON
    logger.info("\n[FASE 3] Gerando Relatório")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    relatorio = {
        "titulo": "Auditoria Fiscal — DEUSDETE 2025",
        "data": datetime.now().isoformat(),
        "contribuinte": {"nome": nome_final, "cpf_cnpj": cpf_final},
        "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
        "resumo": {
            "total_notas": len(todas_nfas),
            "quantidade_total": round(total_qtd, 2),
            "valor_total": round(total_valor, 2)
        },
        "notas": [
            {
                "numero": n.numero,
                "data": n.data,
                "remetente": n.remetente,
                "destinatario": n.destinatario,
                "produto": n.produto,
                "quantidade": round(n.quantidade, 2),
                "valor_unitario": round(n.valor_unitario, 2),
                "valor_total": round(n.valor_total, 2)
            }
            for n in todas_nfas
        ]
    }

    json_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)

    logger.info(f"  ✓ Relatório salvo em: {json_path}")

    # [FASE 4] PDF (opcional)
    logger.info("\n[FASE 4] Geração de PDF")
    try:
        from pdf_engine.orgaudi.report_builder_rl import gerar_laudo_de_json

        dados_pdf = {
            "contribuinte": {
                "nome": nome_final,
                "cpf": cpf_final.replace(".", "").replace("/", "").replace("-", "") if cpf_final else "00000000000",
                "ie": "",
                "municipio": "Tocantins"
            },
            "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
            "notas": [
                {
                    "numero": n.numero,
                    "serie": "1",
                    "data": n.data,
                    "destinatario": n.destinatario,
                    "produto": n.produto,
                    "quantidade": round(n.quantidade, 2),
                    "valor_unitario": round(n.valor_unitario, 2),
                    "valor_total": round(n.valor_total, 2),
                }
                for n in todas_nfas
            ]
        }

        pdf_path = output_dir / f"DEUSDETE_AUDITORIA_{timestamp}.pdf"
        gerar_laudo_de_json(dados_pdf, str(pdf_path), strict_cpf=False)
        logger.info(f"  ✓ PDF gerado: {pdf_path}")
    except Exception as e:
        logger.warning(f"  ⚠ Não foi possível gerar PDF: {e}")

    # [RESUMO]
    logger.info("\n" + "=" * 70)
    logger.info("AUDITORIA CONCLUÍDA!")
    logger.info("=" * 70)
    logger.info(f"\nRelatórios salvos em: {output_dir}/")
    logger.info(f"\nResumo:")
    logger.info(f"  • {len(todas_nfas)} notas fiscais auditadas")
    logger.info(f"  • {total_qtd:.0f} cabeças de gado")
    logger.info(f"  • R$ {total_valor:,.2f} em movimentação")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
