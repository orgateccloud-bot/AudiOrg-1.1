#!/usr/bin/env python3
"""
Parser v2 — extrai CPFs estruturados das NFAs.
Formato: N° | Data | CPF_REM | Nome_REM | CFOP | CPF_DEST | Nome_DEST | Produto | Qtd | V.Unit | V.Total
"""

import json
import re
import pdfplumber
import logging
from pathlib import Path
from datetime import datetime
from typing import List

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("parser_v2")


class NFA:
    def __init__(self, numero, data, remetente_cpf, remetente_nome,
                 cfop, destinatario_cpf, destinatario_nome,
                 produto, qtd, vlr_unit, vlr_total):
        self.numero = numero
        self.data = data
        self.remetente_cpf = remetente_cpf
        self.remetente_nome = remetente_nome
        self.cfop = cfop
        self.destinatario_cpf = destinatario_cpf
        self.destinatario_nome = destinatario_nome
        self.produto = produto
        self.quantidade = qtd
        self.valor_unitario = vlr_unit
        self.valor_total = vlr_total


# Regex para CPF/CNPJ: 000.000.000-00 ou 00.000.000/0000-00
RE_CPF = re.compile(r'^\d{3}\.\d{3}\.\d{3}-\d{2}$')
RE_CNPJ = re.compile(r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$')
RE_CFOP = re.compile(r'^\d\.\d{3}$')


def eh_documento(s: str) -> bool:
    """True se s é CPF ou CNPJ formatado."""
    return bool(RE_CPF.match(s) or RE_CNPJ.match(s))


def limpar_valor(s: str) -> float:
    """Converte string com vírgula/ponto em float."""
    if not s:
        return 0.0
    s = str(s).strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def extrair_nfas(pdf_path: str) -> tuple[List[NFA], str, str]:
    """Extrai NFAs com CPFs estruturados."""

    nfas = []
    nome_contribuinte = ""
    cpf_contribuinte = ""

    with pdfplumber.open(pdf_path) as pdf:
        texto = "\n".join([p.extract_text() or "" for p in pdf.pages])

    # Extrair CPF do contribuinte do cabeçalho
    match_cpf = re.search(r"CNPJ/CPF:\s*([\d./\-]+)", texto)
    if match_cpf:
        cpf_contribuinte = match_cpf.group(1).strip()

    # Processar linhas
    for line in texto.split('\n'):
        parts = line.split()
        if len(parts) < 10:
            continue

        # [0] número, [1] data, [2] cpf_rem, [...] nome_rem, [cfop_idx] cfop,
        # [cfop_idx+1] cpf_dest, [...] nome_dest, [...] produto, [...] qtd, v_unit, v_total

        # Validar: começa com número 7-8 dígitos
        if not re.match(r'^\d{7,8}$', parts[0]):
            continue

        # Validar: data DD/MM/YYYY
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', parts[1]):
            continue

        # Validar: parts[2] é CPF/CNPJ
        if not eh_documento(parts[2]):
            continue

        try:
            numero = parts[0]
            data = parts[1]
            cpf_rem = parts[2]

            # Encontrar CFOP (X.XXX)
            cfop_idx = None
            for i in range(3, min(len(parts), 15)):
                if RE_CFOP.match(parts[i]):
                    cfop_idx = i
                    break

            if not cfop_idx:
                continue

            nome_rem = " ".join(parts[3:cfop_idx])
            cfop = parts[cfop_idx]

            # CPF destinatário (parts[cfop_idx + 1])
            if cfop_idx + 1 >= len(parts) or not eh_documento(parts[cfop_idx + 1]):
                continue
            cpf_dest = parts[cfop_idx + 1]

            # Nome destinatário: até encontrar "BOVINO" (início do produto)
            nome_dest_end = None
            for i in range(cfop_idx + 2, len(parts)):
                if parts[i].upper().startswith("BOVINO"):
                    nome_dest_end = i
                    break

            if not nome_dest_end:
                continue

            nome_dest = " ".join(parts[cfop_idx + 2:nome_dest_end])

            # Produto: de "BOVINO" até número (quantidade)
            produto_end = None
            for i in range(nome_dest_end, len(parts)):
                # Procurar número com vírgula (quantidade ex: "7,00")
                if re.match(r'^[\d.]+,\d{2}$', parts[i]):
                    produto_end = i
                    break

            if not produto_end or produto_end + 2 >= len(parts):
                continue

            produto = " ".join(parts[nome_dest_end:produto_end])

            # Últimas 3 partes: qtd, v_unit, v_total
            qtd = limpar_valor(parts[produto_end])
            vlr_unit = limpar_valor(parts[-2])
            vlr_total = limpar_valor(parts[-1])

            nfa = NFA(
                numero=numero,
                data=data,
                remetente_cpf=cpf_rem,
                remetente_nome=nome_rem,
                cfop=cfop,
                destinatario_cpf=cpf_dest,
                destinatario_nome=nome_dest,
                produto=produto,
                qtd=qtd,
                vlr_unit=vlr_unit,
                vlr_total=vlr_total,
            )
            nfas.append(nfa)

            # Identificar contribuinte
            if "DEUSDETE" in nome_dest.upper():
                nome_contribuinte = nome_dest
            elif "DEUSDETE" in nome_rem.upper():
                nome_contribuinte = nome_rem

        except Exception as e:
            logger.debug(f"Erro ao parsear linha: {e}")
            continue

    return nfas, nome_contribuinte or "DEUSDETE SOARES DA FONSECA", cpf_contribuinte


def main():
    logger.info("=" * 70)
    logger.info("AUDITORIA FISCAL v2 — DEUSDETE 2025 (com CPFs estruturados)")
    logger.info("=" * 70)

    input_dir = Path("./input_pdfs")
    output_dir = Path("./output_relatorios")
    output_dir.mkdir(exist_ok=True)

    pdfs = list(input_dir.glob("*.pdf"))
    logger.info(f"\nEncontrados {len(pdfs)} PDFs\n")

    # [FASE 1] Extração
    logger.info("[FASE 1] Extração de NFAs com CPFs")
    todas_nfas = []
    nome_final = "DEUSDETE SOARES DA FONSECA"
    cpf_final = ""

    for pdf_path in sorted(pdfs):
        logger.info(f"  Processando {pdf_path.name}...")
        nfas, nome, cpf = extrair_nfas(str(pdf_path))

        if nfas:
            todas_nfas.extend(nfas)
            nome_final = nome or nome_final
            cpf_final = cpf or cpf_final
            logger.info(f"    ✓ Extraídas {len(nfas)} NFAs com CPFs")
        else:
            logger.warning(f"    ⚠ Nenhuma NFA extraída")

    if not todas_nfas:
        logger.error("Erro: Nenhuma NFA extraída!")
        return 1

    logger.info(f"\nTotal de NFAs: {len(todas_nfas)}")

    # [FASE 2] Estatísticas
    total_valor = sum(n.valor_total for n in todas_nfas)
    total_qtd = sum(n.quantidade for n in todas_nfas)

    # CPFs únicos
    cpfs_remetentes = set(n.remetente_cpf for n in todas_nfas if n.remetente_cpf)
    cpfs_destinatarios = set(n.destinatario_cpf for n in todas_nfas if n.destinatario_cpf)

    logger.info(f"\n[FASE 2] Estatísticas")
    logger.info(f"  Contribuinte: {nome_final} ({cpf_final})")
    logger.info(f"  Total de notas: {len(todas_nfas)}")
    logger.info(f"  Quantidade: {total_qtd:.1f}")
    logger.info(f"  Valor total: R$ {total_valor:,.2f}")
    logger.info(f"  CPFs únicos (remetentes): {len(cpfs_remetentes)}")
    logger.info(f"  CPFs únicos (destinatários): {len(cpfs_destinatarios)}")

    # [FASE 3] Salvar JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    relatorio = {
        "titulo": "Auditoria Fiscal — DEUSDETE 2025",
        "data": datetime.now().isoformat(),
        "contribuinte": {"nome": nome_final, "cpf_cnpj": cpf_final},
        "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
        "resumo": {
            "total_notas": len(todas_nfas),
            "quantidade_total": round(total_qtd, 2),
            "valor_total": round(total_valor, 2),
            "cpfs_unicos_remetentes": len(cpfs_remetentes),
            "cpfs_unicos_destinatarios": len(cpfs_destinatarios)
        },
        "notas": [
            {
                "numero": n.numero,
                "data": n.data,
                "remetente_cpf": n.remetente_cpf,
                "remetente_nome": n.remetente_nome,
                "cfop": n.cfop,
                "destinatario_cpf": n.destinatario_cpf,
                "destinatario_nome": n.destinatario_nome,
                "produto": n.produto,
                "quantidade": round(n.quantidade, 2),
                "valor_unitario": round(n.valor_unitario, 2),
                "valor_total": round(n.valor_total, 2)
            }
            for n in todas_nfas
        ]
    }

    json_path = output_dir / f"DEUSDETE_AUDITORIA_V2_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(relatorio, f, indent=2, ensure_ascii=False)

    logger.info(f"\n  ✓ JSON salvo: {json_path}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
