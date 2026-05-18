"""
scripts/restaurar_compras_gief.py
═════════════════════════════════
Restaura `qtd_compras` e `valor_compras` dentro de `totais_pdf_gief`
recuperando os valores que estavam em `totais_planilha` na versão pré-migração
(commit 41a11d6).

Motivo: na migração GIEF-only de 2026-05-17, o script removeu `totais_planilha`
sem mover os dados de compras para `totais_pdf_gief`. No novo modelo GIEF-only,
as compras vêm do próprio GIEF (Relação por Destinatário), então devem estar
em `totais_pdf_gief`.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLIENTES_DIR = RAIZ / "scripts" / "clientes"
COMMIT_PRE_MIGRACAO = "41a11d6"


def carregar_versao_antiga(nome_arquivo: str) -> dict | None:
    """Recupera o JSON do cliente como estava no commit pré-migração."""
    try:
        out = subprocess.run(
            ["git", "show", f"{COMMIT_PRE_MIGRACAO}:scripts/clientes/{nome_arquivo}"],
            cwd=str(RAIZ), capture_output=True, text=True, check=False, encoding="utf-8",
        )
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def restaurar(path: Path) -> str:
    """Retorna status: 'ok', 'sem_compras', 'sem_versao_antiga' ou 'ja_tem'."""
    atual = json.loads(path.read_text(encoding="utf-8"))
    gief = atual.get("totais_pdf_gief") or {}
    if "qtd_compras" in gief and "valor_compras" in gief:
        return "ja_tem"

    antigo = carregar_versao_antiga(path.name)
    if antigo is None:
        return "sem_versao_antiga"

    planilha_antiga = antigo.get("totais_planilha") or {}
    qtd_compras = planilha_antiga.get("qtd_compras")
    valor_compras = planilha_antiga.get("valor_compras")
    if qtd_compras is None and valor_compras is None:
        return "sem_compras"

    if qtd_compras is not None:
        gief["qtd_compras"] = qtd_compras
    if valor_compras is not None:
        gief["valor_compras"] = valor_compras
    atual["totais_pdf_gief"] = gief

    path.write_text(
        json.dumps(atual, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return "ok"


def main() -> None:
    arquivos = sorted(CLIENTES_DIR.glob("*.json"))
    contagem = {"ok": 0, "ja_tem": 0, "sem_compras": 0, "sem_versao_antiga": 0}
    for path in arquivos:
        status = restaurar(path)
        contagem[status] += 1
        marker = {"ok": "[OK]", "ja_tem": "[--]", "sem_compras": "[--]",
                  "sem_versao_antiga": "[??]"}[status]
        print(f"  {marker} {path.name}  ({status})")
    print(f"\nTotal: {contagem['ok']} restaurados, {contagem['ja_tem']} já tinham, "
          f"{contagem['sem_compras']} sem compras, "
          f"{contagem['sem_versao_antiga']} sem versão antiga.")


if __name__ == "__main__":
    main()
