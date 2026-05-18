"""
orgaudi.cli
═══════════
Interface de linha de comando: três modos de uso

  • interativo  — perguntas guiadas via console (default sem subcomando)
  • rapido      — argumentos via flags (script-friendly)
  • batch       — processa lote JSON com tratamento tipado de erros

Uso direto:
    python -m orgaudi rapido --nome "..." --cpf "..." --inicio ...
    python -m orgaudi batch lote.json
    python -m orgaudi interativo

Dependências internas: domain, validators, report_builder
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from decimal import Decimal

from .domain import (
    CPFInvalidoError,
    Contribuinte,
    NaturezaNota,
    NotaFiscal,
    Periodo,
)
from .report_builder_rl import (
    LaudoOrgAudi,
    _parse_data,
    _validar_cpf_obrigatorio,
    carregar_notas_de_json,
    gerar_laudo_de_json,
)
from .validators import validar_cpf


logger = logging.getLogger("orgaudi")


# ═══════════════════════════════════════════════════════════════════════════════
#  MODO INTERATIVO
# ═══════════════════════════════════════════════════════════════════════════════

def _input(label: str, default: str = "", validador=None) -> str:
    suf = f" [{default}]" if default else ""
    while True:
        valor = input(f"  {label}{suf}: ").strip() or default
        if validador and not validador(valor):
            print(f"     ✗ valor inválido — tente novamente")
            continue
        return valor


def modo_interativo() -> int:
    print("═" * 70)
    print("  OrgAudi 1.0 — Gerador de Laudo (modo interativo)")
    print("  ORGATEC CONTABILIDADE E AUDITORIA")
    print("═" * 70)

    print("\n[1/3] DADOS DO CONTRIBUINTE")
    nome = _input("Nome completo", validador=lambda x: len(x) >= 5)
    cpf = _input("CPF", validador=validar_cpf)
    ie = _input("Inscrição Estadual (opcional)")
    municipio = _input("Município", default="Formoso")
    estado = _input("Estado", default="GO")

    print("\n  Categoria previdenciária (afeta alíquota Funrural):")
    print("    1 = PF Patronal (default — produtor rural com empregados)")
    print("    2 = PF Segurado Especial (agricultor familiar / economia familiar)")
    print("    3 = PJ (pessoa jurídica)")
    cat_escolha = _input("Escolha [1/2/3]", default="1")
    eh_pj = (cat_escolha == "3")
    eh_segurado_especial = (cat_escolha == "2")

    print("\n[2/3] PERÍODO AUDITADO")
    ano_atual = date.today().year - 1
    inicio = _input(f"Data de início (YYYY-MM-DD)",
                    default=f"{ano_atual}-01-01")
    fim = _input(f"Data de fim (YYYY-MM-DD)",
                 default=f"{ano_atual}-12-31")

    print("\n[3/3] DADOS DAS NOTAS FISCAIS")
    print("  → Forneça caminho do arquivo JSON com a lista de notas.")
    print("    Formato exemplo em: contribuintes_batch.json")
    notas_arq = _input("Arquivo JSON de notas (ou ENTER para pular)")

    saida = _input("Caminho do PDF de saída",
                   default=f"laudo_{cpf.replace('.','').replace('-','')}.pdf")

    contrib = Contribuinte(nome=nome, cpf=cpf, ie=ie,
                            municipio=municipio, estado=estado,
                            eh_pj=eh_pj,
                            eh_segurado_especial=eh_segurado_especial)
    periodo = Periodo(_parse_data(inicio), _parse_data(fim))

    notas = carregar_notas_de_json(notas_arq) if notas_arq else []
    if not notas:
        print("\n  ⚠ Sem notas — gerando laudo apenas com cabeçalho/identificação.")
        print("     Não recomendado em auditoria real.")
        return 1

    laudo = LaudoOrgAudi(contribuinte=contrib, periodo=periodo, notas=notas)
    laudo.processar()
    laudo.gerar_pdf(saida)

    print("\n" + "═" * 70)
    print(f"  ✓ Laudo gerado: {saida}")
    print(f"  ✓ Hash:         {laudo.hash_doc}")
    print("═" * 70)
    print(f"\n{laudo.resumo_executivo()}\n")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  MODO RÁPIDO (CLI)
# ═══════════════════════════════════════════════════════════════════════════════

def modo_rapido(args) -> int:
    # Valida CPF antes de qualquer processamento (consistência com modo interativo)
    try:
        _validar_cpf_obrigatorio(args.cpf, contexto=f"contribuinte {args.nome}")
    except CPFInvalidoError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    contrib = Contribuinte(
        nome=args.nome, cpf=args.cpf,
        ie=args.ie or "", municipio=args.municipio or "",
        estado=args.estado or "GO",
        eh_pj=getattr(args, "pj", False),
        eh_segurado_especial=getattr(args, "segurado_especial", False))
    periodo = Periodo(
        inicio=_parse_data(args.inicio),
        fim=_parse_data(args.fim))

    notas = carregar_notas_de_json(args.notas) if args.notas else []
    if not notas:
        print("✗ É necessário fornecer --notas (arquivo JSON)", file=sys.stderr)
        return 1

    laudo = LaudoOrgAudi(contribuinte=contrib, periodo=periodo, notas=notas)
    laudo.processar()
    laudo.gerar_pdf(args.out)

    print(f"✓ {args.out}")
    print(f"  Hash: {laudo.hash_doc}")
    print(f"  {laudo.resumo_executivo()}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
#  MODO BATCH (vários contribuintes em sequência)
# ═══════════════════════════════════════════════════════════════════════════════

def modo_batch(arquivo_lote: str) -> int:
    """
    Formato do JSON de lote:
      [
        {
          "contribuinte": {...},
          "periodo": {...},
          "notas": [...] OU "notas_arquivo": "caminho.json",
          "saida": "laudo_X.pdf"
        },
        ...
      ]

    Erros são registrados em laudo_erros_YYYYMMDD_HHMMSS.log para rastreabilidade.
    """
    with open(arquivo_lote, encoding="utf-8") as f:
        lote = json.load(f)

    # Log de erros em arquivo dedicado
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"laudo_erros_{timestamp}.log"

    print(f"Processando lote: {len(lote)} laudo(s)")
    print(f"Log de erros: {log_path}")

    sucesso = falha = 0
    erros: list[dict] = []

    for i, item in enumerate(lote, 1):
        saida = item.get("saida") or f"laudo_{i:03d}.pdf"
        nome_contrib = item.get("contribuinte", {}).get("nome", "?")
        cpf_contrib = item.get("contribuinte", {}).get("cpf", "?")

        try:
            dados = dict(item)
            dados.pop("saida", None)
            if "notas_arquivo" in item:
                dados["notas"] = [
                    {"numero": n.numero,
                     "data": n.data.isoformat(),
                     "natureza": n.natureza.value,
                     "valor": float(n.valor),
                     "cabecas": n.cabecas,
                     "remetente_cpf": n.remetente_cpf,
                     "remetente_nome": n.remetente_nome,
                     "destinatario_cpf": n.destinatario_cpf,
                     "destinatario_nome": n.destinatario_nome}
                    for n in carregar_notas_de_json(item["notas_arquivo"])
                ]
                dados.pop("notas_arquivo")
            res = gerar_laudo_de_json(dados, saida)
            print(f"  [{i:3d}/{len(lote)}] ✓ {saida}  hash={res['hash']}")
            sucesso += 1

        except CPFInvalidoError as e:
            tipo = "CPF_INVALIDO"
            msg = str(e)
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

        except FileNotFoundError as e:
            tipo = "ARQUIVO_NAO_ENCONTRADO"
            msg = str(e)
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

        except (KeyError, ValueError) as e:
            tipo = "DADOS_INVALIDOS"
            msg = f"{type(e).__name__}: {e}"
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

        except Exception as e:
            tipo = "ERRO_INESPERADO"
            msg = f"{type(e).__name__}: {e}"
            print(f"  [{i:3d}/{len(lote)}] ✗ {tipo}: {msg}", file=sys.stderr)
            erros.append({
                "indice": i, "tipo": tipo,
                "contribuinte": nome_contrib, "cpf": cpf_contrib,
                "saida_pretendida": saida, "erro": msg,
            })
            falha += 1

    # Grava log de erros se houver falhas
    if erros:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# OrgAudi 1.0 — Log de erros do lote\n")
            f.write(f"# Arquivo: {arquivo_lote}\n")
            f.write(f"# Timestamp: {timestamp}\n")
            f.write(f"# Total: {len(lote)} | Sucesso: {sucesso} | Falha: {falha}\n\n")
            json.dump(erros, f, indent=2, ensure_ascii=False)

    print(f"\nConcluído: {sucesso} sucesso(s), {falha} falha(s)")
    if erros:
        print(f"Detalhes em: {log_path}")
    return 0 if falha == 0 else 2


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OrgAudi 1.0 — Gerador de Laudo de Auditoria Forense",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = parser.add_subparsers(dest="modo")

    sub.add_parser("interativo", help="Modo interativo (padrão)")

    rp = sub.add_parser("rapido", help="Modo rápido via CLI")
    rp.add_argument("--nome", required=True)
    rp.add_argument("--cpf", required=True)
    rp.add_argument("--ie")
    rp.add_argument("--municipio")
    rp.add_argument("--estado")
    rp.add_argument("--inicio", required=True)
    rp.add_argument("--fim", required=True)
    rp.add_argument("--notas", required=True, help="JSON com a lista de notas")
    rp.add_argument("--out", required=True, help="Caminho do PDF de saída")
    rp.add_argument("--pj", action="store_true",
                    help="Contribuinte é Pessoa Jurídica (alíquotas Funrural 2,05%%/2,23%%)")
    rp.add_argument("--segurado-especial", action="store_true",
                    dest="segurado_especial",
                    help="PF Segurado Especial (agricultura familiar) — Funrural mantém 1,5%%")

    ba = sub.add_parser("batch", help="Modo batch — múltiplos contribuintes")
    ba.add_argument("arquivo", help="JSON de lote")

    args = parser.parse_args(argv)

    if args.modo is None or args.modo == "interativo":
        return modo_interativo()
    if args.modo == "rapido":
        return modo_rapido(args)
    if args.modo == "batch":
        return modo_batch(args.arquivo)
    return 0


