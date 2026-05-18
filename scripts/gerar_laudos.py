"""
scripts/gerar_laudos.py
═══════════════════════
Gerador multi-cliente de laudos OrgAudi.

USO:
    python scripts/gerar_laudos.py genis_2025
    python scripts/gerar_laudos.py --todos
    python scripts/gerar_laudos.py --listar

Gera para cada cliente:
    outputs/<slug>/auditoria_cruzada.json      — dados completos
    outputs/<slug>/auditoria_v2.json           — dados simplificados (sem catálogos)
    outputs/<slug>/laudo_completo.pdf          — PDF completo
    outputs/<slug>/laudo_simplificado.pdf      — PDF simplificado (novo modelo)
    outputs/<slug>/planilha_gado_ir_v5.docx
    outputs/<slug>/relatorio_resumo.md
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.schemas.cruzamento import CruzamentoRequest
from api.services.auditoria_cruzada import processar_auditoria_cruzada
from api.services.auditoria_cruzada_pdf import gerar_pdf_auditoria_cruzada

CLIENTES_DIR = RAIZ / "scripts" / "clientes"
OUTPUTS_DIR  = RAIZ / "outputs"

CHAVES_EXCLUIR = {
    "catalogo_anomalias",
    "eixos_tipologias",
    "tipologias_consideradas",
    "regra_especial_1",
    "regra_5_cruzamentos_externos",
}


def listar_clientes() -> list[str]:
    return sorted(
        p.stem for p in CLIENTES_DIR.glob("*.json")
        if not p.stem.startswith("_") and p.stem != "README"
    )


def carregar_cliente(slug: str) -> dict:
    path = CLIENTES_DIR / f"{slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"Cliente não encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def calcular_hash_canonico(resultado: dict) -> tuple[str, str]:
    """Retorna (payload_json, sha256_hex) sobre os indicadores principais."""
    ind = resultado["indicadores_principais"]
    c   = resultado["contribuinte"]
    p   = resultado["periodo"]

    f4 = (
        ind["F4_RECEITA_BRUTA"]["valor"]
        if "F4_RECEITA_BRUTA" in ind
        else ind["F1_RECEITA_IMEDIATA"]["valor"]
    )

    payload = json.dumps({
        "F1":        ind["F1_RECEITA_IMEDIATA"]["valor"],
        "F2":        ind["F2_TRANSITO"]["valor"],
        "F4":        f4,
        "F5":        ind["F5_RESULTADO_RURAL"]["valor"],
        "F6":        ind["F6_COMPRAS"]["valor"],
        "cpf":       c["cpf"],
        "data_audit": str(datetime.now(timezone.utc).date()),
        "fim":       p["fim"],
        "inicio":    p["inicio"],
        "nome":      c["nome"],
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def simplificar_resultado(resultado: dict) -> dict:
    """Remove seções de catálogo e regras do JSON completo."""
    return {k: v for k, v in resultado.items() if k not in CHAVES_EXCLUIR}


def gerar_para_cliente(slug: str) -> Path:
    payload = carregar_cliente(slug)
    nome    = payload.get("contribuinte_nome", slug)
    print(f"\n=== {nome} ===")

    pasta = OUTPUTS_DIR / slug
    pasta.mkdir(parents=True, exist_ok=True)

    # 1. Processar auditoria → JSON completo
    request = CruzamentoRequest.model_validate(payload)
    resultado = processar_auditoria_cruzada(request)

    # 2. Calcular hash SHA-256 canônico
    payload_str, hash_hex = calcular_hash_canonico(resultado)
    resultado["audit_hash"]   = hash_hex
    resultado["payload_hash"] = payload_str

    # 3. JSON completo
    (pasta / "auditoria_cruzada.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [OK] auditoria_cruzada.json")

    # 4. JSON simplificado (sem catálogos e regras)
    resultado_v2 = simplificar_resultado(resultado)
    (pasta / "auditoria_v2.json").write_text(
        json.dumps(resultado_v2, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [OK] auditoria_v2.json")

    # 5. PDF simplificado (novo modelo com hash canônico)
    pdf_simples = gerar_pdf_auditoria_cruzada(resultado_v2, modo="simplificado")
    (pasta / "laudo_simplificado.pdf").write_bytes(pdf_simples)
    print(f"  [OK] laudo_simplificado.pdf ({len(pdf_simples):,} bytes)")

    # 6. PDF completo
    pdf_completo = gerar_pdf_auditoria_cruzada(resultado, modo="completo")
    (pasta / "laudo_completo.pdf").write_bytes(pdf_completo)
    print(f"  [OK] laudo_completo.pdf ({len(pdf_completo):,} bytes)")

    # 7. Copiar para laudos_pdf canônico
    laudos_dir = RAIZ / "reports_nfa" / "laudos_pdf"
    laudos_dir.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"Laudo_{slug.upper().split('_')[0]}.pdf"
    (laudos_dir / nome_arquivo).write_bytes(pdf_simples)
    print(f"  [OK] reports_nfa/laudos_pdf/{nome_arquivo}")

    print(f"  SHA-256 : {hash_hex}")
    return pasta


def main() -> None:
    args = sys.argv[1:]

    if not args or "--ajuda" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    if "--listar" in args:
        clientes = listar_clientes()
        print(f"{len(clientes)} clientes disponíveis:")
        for c in clientes:
            print(f"  {c}")
        sys.exit(0)

    if "--todos" in args:
        clientes = listar_clientes()
        print(f"Gerando laudos para {len(clientes)} clientes...")
        erros = []
        for slug in clientes:
            try:
                gerar_para_cliente(slug)
            except Exception as e:
                print(f"  [ERRO] {slug}: {e}")
                erros.append(slug)
        if erros:
            print(f"\n{len(erros)} erro(s): {erros}")
        else:
            print(f"\nTodos os laudos gerados com sucesso.")
        return

    # Cliente específico
    slug = args[0]
    try:
        pasta = gerar_para_cliente(slug)
        print(f"\nSaída: {pasta}")
    except FileNotFoundError as e:
        print(f"Erro: {e}")
        print(f"Clientes disponíveis: {listar_clientes()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
