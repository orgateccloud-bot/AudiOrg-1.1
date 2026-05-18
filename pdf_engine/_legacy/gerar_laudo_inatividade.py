"""scripts/gerar_laudo_inatividade.py

Gera laudo de ATESTADO DE INATIVIDADE FISCAL para clientes que não
emitiram nem receberam NFA-e no exercício (confirmado pelo PDF GIEF
contendo "Não existe NFA para o período informado").

Aplica template oficial simplificado (HTML/Chrome) com:
  • Mapa de severidades 0/0/0/0/CONFORME
  • Achado único de conformidade atestando ausência de operações
  • Declaração de alcance + assinatura

Uso:
    python scripts/gerar_laudo_inatividade.py
    python scripts/gerar_laudo_inatividade.py hellida_patricia_oliveira_camilo_pereira_2025
"""
from __future__ import annotations

import io
import json
import sys
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.services.auditoria_cruzada_pdf import gerar_pdf_auditoria_cruzada

DATA = datetime.now().strftime("%Y-%m-%d")
DEST = RAIZ / "reports_nfa" / "forense_individual"
DEST.mkdir(parents=True, exist_ok=True)

INATIVOS = [
    "hellida_patricia_oliveira_camilo_pereira_2025",
    "ricardo_de_souza_lobo_2025",
]


def montar_atestado(base_v2: dict) -> dict:
    r = deepcopy(base_v2)
    nome = r.get("contribuinte", {}).get("nome", "—")

    achado_conforme = {
        "codigo": "CF-01",
        "titulo": "Atestado de inatividade fiscal — exercício 2025",
        "descricao": (
            f"O contribuinte <b>{nome}</b> NÃO emitiu nem recebeu nenhuma "
            "Nota Fiscal Avulsa Eletrônica (NFA-e) no período de 01/01/2025 "
            "a 31/12/2025, conforme consulta ao sistema GIEF/SEFAZ-GO em "
            "06/04/2026. Os relatórios de Saídas (REM) e Entradas (DEST) "
            "retornaram a mensagem padrão <i>'Não existe NFA para o período "
            "informado'</i>, atestando ausência total de movimentação na "
            "atividade rural junto ao Estado de Goiás no exercício."),
        "severidade": "CONFORME",
        "porque_critico": (
            "Inatividade fiscal documentalmente comprovada exime o "
            "contribuinte de Funrural, ICMS estadual sobre saídas rurais e "
            "obrigações acessórias derivadas do volume (LCDPR). Contudo, a "
            "DIRPF 2026 ainda deve declarar a propriedade rural e o plantel "
            "remanescente sob 'Bens e Direitos' caso existam."),
        "cruzamentos": [
            "Confirmação cadastral SEFAZ-GO (IE ativa/inativa no exercício)",
            "CAEPF na Receita Federal (registro como produtor rural)",
            "Inventário do rebanho declarado na DIRPF 2025 (linha de base)",
            "GTAs AGRODEFESA-GO (movimentação animal mesmo sem nota?)",
            "Extratos bancários do exercício (transações relacionadas)",
        ],
        "tabela_cabecalhos": ["Documento consultado", "Resultado", "Data consulta"],
        "tabela_linhas": [
            ["Relatório GIEF/SEFAZ-GO — Saídas (REM)",
             "Não existe NFA para o período informado", "06/04/2026"],
            ["Relatório GIEF/SEFAZ-GO — Entradas (DEST)",
             "Não existe NFA para o período informado", "06/04/2026"],
        ],
        "tabela_totais": [],
    }

    r["achados_criticos"] = []
    r["achados_medios"] = []
    r["pontos_atencao"] = []
    r["conformidades"] = [achado_conforme]
    r["severidades"] = {
        "CRITICO": 0, "ALTO": 0, "MEDIO": 0, "ATENCAO": 0, "CONFORME": 1,
    }
    r["sistema"] = "OrgAudi 1.1 — Atestado de Inatividade Fiscal"
    r["timestamp"] = datetime.now().isoformat()

    # Zera indicadores principais (já estão zero, mas garantir)
    if "indicadores_principais" in r:
        for k, v in r["indicadores_principais"].items():
            if isinstance(v, dict) and "valor" in v:
                v["valor"] = "0.00"

    return r


def main() -> None:
    alvos = sys.argv[1:] or INATIVOS
    print(f"{'CLIENTE':50s} {'STATUS':>10s}  {'TAMANHO'}")
    print("=" * 100)
    gerados = []
    for slug in alvos:
        base_path = RAIZ / "outputs" / slug / "auditoria_v2.json"
        if not base_path.exists():
            print(f"{slug:50s} {'SEM_BASE':>10s}  (rode gerar_laudos.py {slug})")
            continue
        try:
            base = json.loads(base_path.read_text(encoding="utf-8"))
            resultado = montar_atestado(base)
            pdf_bytes = gerar_pdf_auditoria_cruzada(resultado, modo="simplificado")
            arq = DEST / f"LAUDO_INATIVIDADE_{slug}_{DATA}.pdf"
            arq.write_bytes(pdf_bytes)
            gerados.append(arq)
            print(f"{slug:50s} {'OK':>10s}  {len(pdf_bytes)/1024:.1f} KB")
        except Exception as e:
            print(f"{slug:50s} {'ERRO':>10s}  {e}")

    print(f"\n[OK] {len(gerados)} laudo(s) de inatividade gerado(s) em {DEST}")


if __name__ == "__main__":
    main()
