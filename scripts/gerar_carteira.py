"""scripts/gerar_carteira.py
═══════════════════════════════════════════════════════════════════════════
Pipeline ÚNICO da carteira OrgAudi 1.1 — saída padronizada em
`outputs/<slug>/` para TODOS os clientes (com ou sem operações):

    outputs/<slug>/
      ├── auditoria_v2.json         (schema simplificado 16 chaves
      │                              + achados endurecidos injetados)
      ├── auditoria_cruzada.json    (schema completo 21 chaves)
      ├── laudo_simplificado.pdf    (PDF do schema v2 — modelo oficial)
      └── laudo_completo.pdf        (PDF do schema completo — modelo oficial)

Pipeline:
  1. Base: `gerar_laudos.py` para cada cliente (produz JSONs originais).
  2. Para clientes COM operações: injeta achados endurecidos
     (T-01..T-08 + AN-02..AN-17) lendo ANALISE_FORENSE_HARD + ANOMALIAS_AN18.
  3. Para clientes SEM operações: gera atestado de inatividade (CF-01).
  4. Regrava `auditoria_v2.json` + `laudo_simplificado.pdf` + `laudo_completo.pdf`
     em `outputs/<slug>/` — sobrescreve os arquivos antigos.

Saída única — substitui:
  • scripts/gerar_laudo_forense_hard.py  (writes outputs/<slug>/ direct)
  • scripts/gerar_laudo_inatividade.py   (writes outputs/<slug>/ direct)
  • reports_nfa/forense_individual/      (não usar mais)

Uso:
    python scripts/gerar_carteira.py           # todos os clientes
    python scripts/gerar_carteira.py genis_2025
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Import primeiro (que reassigna stdout) — depois nosso encoding
from scripts._forense_helper import (
    montar_resultado_endurecido,
    _pick_latest,
)
from pdf_engine import gerar_pdf_auditoria_cruzada

OUTPUTS = RAIZ / "outputs"
DATA = datetime.now().strftime("%Y-%m-%d")
ARQ_HARD = _pick_latest("ANALISE_FORENSE_HARD")
ARQ_AN18 = _pick_latest("ANOMALIAS_AN18")


# Slugs em outputs/ que NÃO são clientes reais (modelos, duplicatas)
SLUGS_IGNORAR = {"exemplo_basico", "genis_carlos_luiz_de_oliveira_2025"}


def listar_clientes() -> list[str]:
    """Retorna slugs reais com auditoria_v2.json em outputs/."""
    return sorted(p.parent.name for p in OUTPUTS.glob("*/auditoria_v2.json")
                   if p.parent.name not in SLUGS_IGNORAR)


def montar_atestado_inatividade(base_v2: dict) -> dict:
    """Substitui achados por achado único CF-01 de inatividade fiscal."""
    r = deepcopy(base_v2)
    nome = r.get("contribuinte", {}).get("nome", "—")
    r["achados_criticos"] = []
    r["achados_medios"] = []
    r["pontos_atencao"] = []
    r["severidades"] = {"CRITICO": 0, "ALTO": 0, "MEDIO": 0, "ATENCAO": 0,
                          "CONFORME": 1}
    r["conformidades"] = [{
        "codigo": "CF-01",
        "titulo": "Atestado de inatividade fiscal — exercício 2025",
        "descricao": (
            f"O contribuinte <b>{nome}</b> NÃO emitiu nem recebeu nenhuma NFA-e "
            "no período 01/01/2025 a 31/12/2025, conforme consulta ao sistema "
            "GIEF/SEFAZ-GO. Os relatórios de Saídas (REM) e Entradas (DEST) "
            "retornaram <i>'Não existe NFA para o período informado'</i>, "
            "atestando ausência total de movimentação na atividade rural "
            "junto ao Estado de Goiás no exercício."),
        "severidade": "CONFORME",
        "porque_critico": (
            "Inatividade fiscal comprovada exime o contribuinte de Funrural, "
            "ICMS sobre saídas rurais e obrigações acessórias derivadas do "
            "volume (LCDPR). DIRPF 2026 ainda deve declarar a propriedade "
            "rural e plantel remanescente sob 'Bens e Direitos'."),
        "cruzamentos": [
            "Confirmação cadastral SEFAZ-GO (IE ativa/inativa no exercício)",
            "CAEPF na Receita Federal (registro como produtor rural)",
            "Inventário do rebanho declarado na DIRPF 2025",
            "GTAs AGRODEFESA-GO (movimentação animal mesmo sem nota?)",
            "Extratos bancários do exercício",
        ],
        "tabela_cabecalhos": ["Documento consultado", "Resultado", "Data"],
        "tabela_linhas": [
            ["Relatório GIEF/SEFAZ-GO — Saídas (REM)",
             "Não existe NFA para o período informado", "06/04/2026"],
            ["Relatório GIEF/SEFAZ-GO — Entradas (DEST)",
             "Não existe NFA para o período informado", "06/04/2026"],
        ],
        "tabela_totais": [],
    }]
    r["sistema"] = "OrgAudi 1.1 — Atestado de Inatividade Fiscal"
    r["timestamp"] = datetime.now().isoformat()
    if "indicadores_principais" in r:
        for v in r["indicadores_principais"].values():
            if isinstance(v, dict) and "valor" in v:
                v["valor"] = "0.00"
    return r


def processar_cliente(slug: str, hard_por_slug: dict, an_por_slug: dict,
                       cascatas_por_slug: dict) -> str:
    """Atualiza outputs/<slug>/ com a versão endurecida (ou atestado)."""
    pasta = OUTPUTS / slug
    base_path = pasta / "auditoria_v2.json"
    if not base_path.exists():
        return "sem_base"

    base_v2 = json.loads(base_path.read_text(encoding="utf-8"))
    fh = hard_por_slug.get(slug, {})
    fan = an_por_slug.get(slug, {})
    cascatas = cascatas_por_slug.get(slug, [])

    qtd_notas = fh.get("qtd_notas", 0)
    if qtd_notas == 0:
        resultado_v2 = montar_atestado_inatividade(base_v2)
        modo_msg = "INATIVIDADE"
    else:
        resultado_v2 = montar_resultado_endurecido(base_v2, fh, fan, cascatas)
        modo_msg = "ENDURECIDO"

    # Regrava auditoria_v2.json (com achados endurecidos/atestado)
    base_path.write_text(
        json.dumps(resultado_v2, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # Constrói auditoria_cruzada (completo) — herda + 5 catálogos da base
    base_full_path = pasta / "auditoria_cruzada.json"
    if base_full_path.exists():
        base_full = json.loads(base_full_path.read_text(encoding="utf-8"))
        resultado_full = deepcopy(resultado_v2)
        for k in ("tipologias_consideradas", "regra_especial_1",
                   "regra_5_cruzamentos_externos", "catalogo_anomalias",
                   "eixos_tipologias"):
            if k in base_full:
                resultado_full[k] = base_full[k]
        base_full_path.write_text(
            json.dumps(resultado_full, ensure_ascii=False, indent=2),
            encoding="utf-8")
    else:
        resultado_full = resultado_v2

    # Gera PDFs no template oficial
    pdf_simples = gerar_pdf_auditoria_cruzada(resultado_v2, modo="simplificado")
    pdf_completo = gerar_pdf_auditoria_cruzada(resultado_full, modo="completo")
    (pasta / "laudo_simplificado.pdf").write_bytes(pdf_simples)
    (pasta / "laudo_completo.pdf").write_bytes(pdf_completo)

    return f"{modo_msg} ({len(pdf_simples)/1024:.0f}/{len(pdf_completo)/1024:.0f} KB)"


def main() -> None:
    if not ARQ_HARD.exists() or not ARQ_AN18.exists():
        print(f"[ERRO] JSONs forenses ausentes — rode antes:\n"
               f"  python scripts/analise_forense_completa.py\n"
               f"  python scripts/analise_anomalias_18.py")
        return

    hard = json.loads(ARQ_HARD.read_text(encoding="utf-8"))
    an18 = json.loads(ARQ_AN18.read_text(encoding="utf-8"))
    hard_por_slug = {h["slug"]: h for h in hard}
    an_por_slug = {a["slug"]: a for a in an18["por_cliente"]}

    cascatas_por_slug = {}
    cpf_para_slug = {a.get("contribuinte_cpf"): a["slug"]
                      for a in an18["por_cliente"] if a.get("contribuinte_cpf")}
    for c in an18.get("an17_cascata", []):
        slug_a = cpf_para_slug.get(c["a_cpf"])
        if slug_a:
            cascatas_por_slug.setdefault(slug_a, []).append(c)

    alvos = sys.argv[1:] or listar_clientes()
    print(f"{'CLIENTE':50s} {'STATUS':>10s}  {'SAÍDA'}")
    print("=" * 100)
    gerados = 0
    for slug in alvos:
        try:
            status = processar_cliente(slug, hard_por_slug, an_por_slug,
                                          cascatas_por_slug)
            print(f"{slug:50s} {status:>10s}  outputs/{slug}/")
            if not status.startswith("sem_base"):
                gerados += 1
        except Exception as e:
            print(f"{slug:50s} {'ERRO':>10s}  {e}")

    print(f"\n[OK] {gerados} cliente(s) atualizado(s) em outputs/<slug>/")
    print("     • auditoria_v2.json + auditoria_cruzada.json (com achados endurecidos)")
    print("     • laudo_simplificado.pdf + laudo_completo.pdf (template oficial)")


if __name__ == "__main__":
    main()
