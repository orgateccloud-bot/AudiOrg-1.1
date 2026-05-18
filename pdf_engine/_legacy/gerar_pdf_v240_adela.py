"""Gera laudo OrgAudi v2.4 (motor ReportLab) para ADELA.

Usa LaudoOrgAudi -> 11 paginas com design profissional + two-pass build
para paginacao correta. Diferente do v2.5 (HTML/Chrome), nao depende de
Chrome instalado.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdf_engine import LaudoOrgAudi
from pdf_engine.orgaudi.domain import Contribuinte, NaturezaNota, NotaFiscal, Periodo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("adela-v240")

ADELA_CPF = "069.311.951-90"
ADELA_NOME = "ADELA FERNANDA SILVA SANTOS"
ADELA_IE = "115254234"

NATUREZA_MAP = {
    "VENDA": NaturezaNota.VENDA,
    "TRANSFERENCIA": NaturezaNota.TRANSFERENCIA,
    "REMESSA/LEILAO": NaturezaNota.LEILAO,
}

# (numero, data_br, natureza, valor, rem_cpf, rem_nome, dest_cpf, dest_nome, cabecas)
NOTAS = [
    # DEST - ADELA destinataria (compras)
    ("25627606", "18/06/2025", "VENDA", 361080.00, "577.749.941-49", "DIVINO FERNANDES DOS SANTOS",   ADELA_CPF, ADELA_NOME, 124),
    ("25661445", "24/06/2025", "VENDA",  12320.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",      ADELA_CPF, ADELA_NOME,   4),
    ("25753672", "07/07/2025", "VENDA",  21240.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",      ADELA_CPF, ADELA_NOME,   6),
    ("25813736", "16/07/2025", "VENDA", 105840.00, "604.849.181-68", "ADMILSON DA CAMARA ROMEIRO",    ADELA_CPF, ADELA_NOME,  42),
    ("25898987", "30/07/2025", "VENDA",  82640.00, "604.849.181-68", "ADMILSON DA CAMARA ROMEIRO",    ADELA_CPF, ADELA_NOME,  31),
    ("26058508", "25/08/2025", "VENDA",  47140.00, "104.956.191-08", "ANDRE FERNANDES DA SILVA",      ADELA_CPF, ADELA_NOME,  17),
    ("26443937", "31/10/2025", "VENDA",  25200.00, "047.599.621-66", "JOAO WESLEY NOBREGA ROMEIRO",   ADELA_CPF, ADELA_NOME,  10),

    # REM - ADELA remetente (vendas)
    ("25177992", "03/04/2025", "VENDA",          100858.38, ADELA_CPF, ADELA_NOME, "577.749.941-49",     "DIVINO FERNANDES DOS SANTOS",     48),
    ("25471529", "26/05/2025", "VENDA",           31068.91, ADELA_CPF, ADELA_NOME, "604.849.181-68",     "ADMILSON DA CAMARA ROMEIRO",      10),
    ("25510606", "01/06/2025", "TRANSFERENCIA",   79859.79, ADELA_CPF, ADELA_NOME, "047.599.621-66",     "JOAO WESLEY NOBREGA ROMEIRO",     27),
    ("25715829", "01/07/2025", "REMESSA/LEILAO",  34580.00, ADELA_CPF, ADELA_NOME, "27.372.042/0001-00", "LEILOES TROMBAS LTDA-ME",         13),
    ("25749054", "07/07/2025", "VENDA",            3599.00, ADELA_CPF, ADELA_NOME, "598.544.561-53",     "JANE QUEIROZ DE ARAUJO SILVA",     1),
    ("25766138", "09/07/2025", "VENDA",          170800.00, ADELA_CPF, ADELA_NOME, "104.956.191-08",     "ANDRE FERNANDES DA SILVA",        60),
    ("25813404", "16/07/2025", "REMESSA/LEILAO", 105840.00, ADELA_CPF, ADELA_NOME, "604.849.181-68",     "ADMILSON DA CAMARA ROMEIRO",      42),
    ("25820292", "17/07/2025", "VENDA",           39204.00, ADELA_CPF, ADELA_NOME, "036.170.761-49",     "OTAVIO GONCALVES MATIAS",         18),
    ("25855069", "23/07/2025", "VENDA",          101940.00, ADELA_CPF, ADELA_NOME, "104.956.191-08",     "ANDRE FERNANDES DA SILVA",        45),
    ("25868512", "24/07/2025", "REMESSA/LEILAO",  59660.00, ADELA_CPF, ADELA_NOME, "33.442.191/0001-09", "BOI FORTE LEILOES LTDA",          19),
    ("25906436", "31/07/2025", "VENDA",           36300.00, ADELA_CPF, ADELA_NOME, "010.919.661-92",     "HALISON MACEDO DOS SANTOS",       11),
    ("25910879", "31/07/2025", "REMESSA/LEILAO",  32760.00, ADELA_CPF, ADELA_NOME, "33.442.191/0001-09", "BOI FORTE LEILOES LTDA",          13),
    ("25932999", "05/08/2025", "VENDA",           26400.00, ADELA_CPF, ADELA_NOME, "057.395.221-37",     "ANA PAULA FERREIRA DE MOURA",      8),
    ("25951265", "07/08/2025", "VENDA",           13100.00, ADELA_CPF, ADELA_NOME, "301.950.551-87",     "LUIZ CARLOS DE PAIVA",             5),
    ("25955577", "07/08/2025", "VENDA",           20960.00, ADELA_CPF, ADELA_NOME, "460.241.666-72",     "ERNANE DE ASSIS FREITAS",          8),
    ("26405785", "23/10/2025", "VENDA",           48300.00, ADELA_CPF, ADELA_NOME, "027.987.731-56",     "GUSTAVO VIEIRA DE OLIVEIRA",      15),
    ("26476918", "06/11/2025", "REMESSA/LEILAO",  15120.00, ADELA_CPF, ADELA_NOME, "33.442.191/0001-09", "BOI FORTE LEILOES LTDA",           6),
    ("26514714", "13/11/2025", "VENDA",            6240.00, ADELA_CPF, ADELA_NOME, "890.755.441-20",     "SERGIO FLAUZINO DA SILVA",         2),
    ("26536562", "18/11/2025", "VENDA",           10920.00, ADELA_CPF, ADELA_NOME, "225.751.701-68",     "ANTONIO RODRIGUES NETO",           4),
]


def _data_iso(data_br: str) -> date:
    return datetime.strptime(data_br, "%d/%m/%Y").date()


def construir_notas() -> list[NotaFiscal]:
    return [
        NotaFiscal(
            numero=num,
            data=_data_iso(data_br),
            natureza=NATUREZA_MAP[nat],
            valor=Decimal(str(valor)),
            cabecas=cab,
            remetente_cpf=rem_cpf,
            remetente_nome=rem_nome,
            destinatario_cpf=dest_cpf,
            destinatario_nome=dest_nome,
        )
        for num, data_br, nat, valor, rem_cpf, rem_nome, dest_cpf, dest_nome, cab in NOTAS
    ]


def main() -> Path:
    print("[1/4] Construindo NotaFiscal[]...")
    notas = construir_notas()
    print(f"      OK - {len(notas)} notas")

    print("[2/4] Configurando Contribuinte + Periodo...")
    contribuinte = Contribuinte(
        nome=ADELA_NOME,
        cpf=ADELA_CPF,
        ie=ADELA_IE,
        municipio="TROMBAS",
        estado="GO",
        eh_pj=False,
        eh_segurado_especial=False,
    )
    periodo = Periodo(
        inicio=date(2025, 1, 1),
        fim=date(2025, 12, 31),
    )

    print("[3/4] Processando laudo v240 (ReportLab) - testes T-01..T-08...")
    laudo = LaudoOrgAudi(
        contribuinte=contribuinte,
        periodo=periodo,
        notas=notas,
    )
    laudo.processar()

    # Estatisticas
    print(f"      Achados sugeridos: {len(laudo.achados)}")
    sev_count = {}
    for a in laudo.achados:
        sev_count[a.severidade.value] = sev_count.get(a.severidade.value, 0) + 1
    for sev, n in sorted(sev_count.items()):
        print(f"        - {sev}: {n}")
    print(f"      Hash: {laudo.hash_doc[:16]}...")

    print("[4/4] Gerando PDF (two-pass ReportLab)...")
    saida = Path("reports_nfa") / f"laudo_v240_adela_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    saida.parent.mkdir(parents=True, exist_ok=True)
    laudo.gerar_pdf(str(saida))

    size_kb = saida.stat().st_size / 1024
    print(f"\nPDF v240 gerado: {saida}")
    print(f"Tamanho: {size_kb:.1f} KB")
    return saida


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Falha: %s", exc)
        sys.exit(1)
