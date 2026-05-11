"""Re-audita apenas o produtor GENIS — usa o pipeline completo S1..S7
com o token_router já redistribuído (Sonnet base + Opus escalado).

Saída: reports_nfa/laudos_pdf/Laudo_GENIS.pdf + Laudo_GENIS.json
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Carrega config.env antes de qualquer import LLM
_CONFIG = ROOT / "config.env"
if _CONFIG.exists():
    for linha in _CONFIG.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip('"').strip("'"))

from scripts.auditar_lote_completo_pdf import auditar_um

PASTA = Path(r"C:\Users\Veloso\Desktop\NFE_GADO_2026\ARQUIVO_2026_RESUMO_DE_NFE_GADO_2026")


async def main() -> int:
    from horizon_blue_one.core.orchestrator import Orchestrator
    from horizon_blue_one.nfa_bridge import agrupar_pdfs_por_produtor

    grupos = agrupar_pdfs_por_produtor(PASTA)
    if "GENIS" not in grupos:
        print(f"ERRO: GENIS não encontrado nos grupos. Disponíveis: {sorted(grupos)}")
        return 1

    pdfs = grupos["GENIS"]
    rem = len(pdfs.get("REMETENTE", []))
    dst = len(pdfs.get("DESTINATARIO", []))
    print(f"Reauditando GENIS: REM={rem} DEST={dst}\n")

    orch = Orchestrator()
    r = await auditar_um("GENIS", pdfs, orch)

    print(f"\n{'='*78}")
    print(f"Produtor : {r.get('nome_real') or 'GENIS'}")
    print(f"CPF      : {r.get('cpf')}")
    print(f"Notas    : {r.get('n_notas')}")
    print(f"Score    : {r.get('score_precalc')}")
    print(f"PF       : {r.get('pf')}")
    print(f"Tokens   : {r.get('tokens_consumidos')}")
    print(f"Custo    : USD {r.get('custo_usd_estimado')}")
    print(f"Latência : {r.get('latencia_ms')} ms")
    print(f"PDF      : {r.get('pdf')}")
    print(f"Parecer  : {r.get('parecer_json')}")
    for e in r.get("erros", []):
        print(f"[ERR {e.get('etapa')}] {e.get('erro')}")
    print(f"{'='*78}\n")

    return 0 if r.get("pdf") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
