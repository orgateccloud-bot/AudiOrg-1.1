"""
scripts/restaurar_mensais.py
═════════════════════════════
Restaura `vendas_mensais`, `remessas_mensais`, `compras_mensais` em cada
cliente, recuperando os valores do commit pré-migração GIEF-only (41a11d6).

Motivo: a migração GIEF-only removeu esses 3 arrays do JSON do cliente, mas
o modelo de laudo (LAUDO_GENIS_v2_final.pdf — modelo de referência aprovado)
exige a Planilha de Gado IR com DETALHAMENTO MENSAL (não só totais).
Reativar os arrays permite o `_pagina_planilha_gado_ir` renderizar as tabelas
mês a mês como no modelo.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLIENTES_DIR = RAIZ / "scripts" / "clientes"
COMMIT_PRE_MIGRACAO = "41a11d6"
CHAVES_MENSAIS = ("vendas_mensais", "remessas_mensais", "compras_mensais")


def versao_antiga(nome: str) -> dict | None:
    out = subprocess.run(
        ["git", "show", f"{COMMIT_PRE_MIGRACAO}:scripts/clientes/{nome}"],
        cwd=str(RAIZ), capture_output=True, text=True, check=False, encoding="utf-8",
    )
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except Exception:
        return None


def restaurar(path: Path) -> str:
    atual = json.loads(path.read_text(encoding="utf-8"))
    if any(k in atual for k in CHAVES_MENSAIS):
        return "ja_tem"

    antigo = versao_antiga(path.name)
    if antigo is None:
        return "sem_versao_antiga"

    movidos = 0
    for chave in CHAVES_MENSAIS:
        valor = antigo.get(chave) or []
        if valor:
            atual[chave] = valor
            movidos += 1
    if movidos == 0:
        return "sem_dados"

    path.write_text(
        json.dumps(atual, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return f"ok ({movidos} arrays)"


def main() -> None:
    arquivos = sorted(CLIENTES_DIR.glob("*.json"))
    cont = {"ok": 0, "ja_tem": 0, "sem_dados": 0, "sem_versao_antiga": 0}
    for p in arquivos:
        status = restaurar(p)
        if status.startswith("ok"):
            cont["ok"] += 1
        else:
            cont[status] = cont.get(status, 0) + 1
        print(f"  [{status}] {p.name}")
    print(f"\nTotal: {cont}")


if __name__ == "__main__":
    main()
