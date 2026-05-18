"""
scripts/migrar_clientes_gief_only.py
═════════════════════════════════════
Migra os JSONs de cliente em scripts/clientes/ do formato antigo
(com Planilha IR v5) para o novo formato GIEF-only.

Mudanças aplicadas em cada arquivo:
  • Remove `totais_planilha`
  • Remove `vendas_mensais`, `remessas_mensais`, `compras_mensais`
  • Atualiza `_meta.descricao` para indicar modo GIEF-only (quando existe)
  • Preserva `totais_pdf_gief`, achados_criticos, identificação e período

Os arquivos `_modelo_cliente.json` e `exemplo_basico.json` também são migrados.
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLIENTES_DIR = RAIZ / "scripts" / "clientes"

CHAVES_A_REMOVER = (
    "totais_planilha",
    "vendas_mensais",
    "remessas_mensais",
    "compras_mensais",
)


def migrar_arquivo(path: Path) -> bool:
    """Retorna True se o arquivo foi modificado."""
    dados = json.loads(path.read_text(encoding="utf-8"))

    if not any(k in dados for k in CHAVES_A_REMOVER):
        return False  # já está no formato GIEF-only

    for chave in CHAVES_A_REMOVER:
        dados.pop(chave, None)

    # Atualiza meta (apenas se já existir e mencionar Planilha)
    meta = dados.get("_meta") or {}
    desc = meta.get("descricao", "")
    if "Planilha" in desc or "cruzada" in desc.lower():
        meta["descricao"] = desc + " — migrado para GIEF-only"
        dados["_meta"] = meta

    path.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def main() -> None:
    arquivos = sorted(CLIENTES_DIR.glob("*.json"))
    migrados = 0
    inalterados = 0
    for path in arquivos:
        if migrar_arquivo(path):
            migrados += 1
            print(f"  [OK] {path.name}")
        else:
            inalterados += 1
            print(f"  [--] {path.name}  (já GIEF-only)")
    print(f"\nTotal: {migrados} migrados, {inalterados} inalterados, {len(arquivos)} arquivos.")


if __name__ == "__main__":
    main()
