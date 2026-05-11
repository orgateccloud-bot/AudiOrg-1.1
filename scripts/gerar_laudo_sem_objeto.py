"""Gera laudo PDF para produtores sem NFAs no período (auditoria sem objeto).

Casos do lote 2026-05-11: HELLIDA, RICARDO LOBO.

Shim sobre `pdf_engine.gerar_laudo_sem_objeto_v250` — toda a lógica de
template/ctx fica dentro do pacote (pdf_engine/orgaudi_v250/sem_objeto.py).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pdf_engine import gerar_laudo_sem_objeto_v250

DESTINO = ROOT / "reports_nfa" / "laudos_pdf"

CASOS = [
    ("HELLIDA",      "024.979.491-82"),
    ("RICARDO LOBO", "470.774.761-20"),
]

PERIODO_INICIO = date(2026, 1, 1)
PERIODO_FIM    = date(2026, 12, 31)


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nome, cpf in CASOS:
        slug = nome.replace(" ", "_")
        saida = DESTINO / f"Laudo_{slug}.pdf"
        try:
            gerar_laudo_sem_objeto_v250(
                cliente_nome=nome,
                cliente_cpf=cpf,
                saida=saida,
                periodo_inicio=PERIODO_INICIO,
                periodo_fim=PERIODO_FIM,
            )
            tam_kb = saida.stat().st_size / 1024
            print(f"[OK]   {nome:14} -> {saida.name} ({tam_kb:.1f} KB)")
        except Exception as exc:
            print(f"[ERRO] {nome:14}: {type(exc).__name__}: {exc}")
            return 1
    print(f"\nTimestamp: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
