"""scripts/modelo_pdf_demo.py
═══════════════════════════════════════════════════════════════════════════
EXEMPLO STANDALONE — Reproduz o MODELO de PDF do laudo simplificado.

Esse script é o "ponto de entrada mínimo" para gerar um PDF idêntico ao
modelo `laudo_simplificado.pdf` da ORGATEC. Mostra a estrutura completa
do payload (schema auditoria_v2) e chama o motor oficial.

═══ ARQUITETURA DO MOTOR ═══════════════════════════════════════════════════

Motor (existente no projeto):
  api/services/auditoria_cruzada_pdf.py   ← gerar_pdf_auditoria_cruzada()
    └── pdf_engine/orgaudi_v240/styles.py ← paleta + helpers ReportLab
        ├── _render_chrome()              ← cabeçalho azul + banda dourada
        ├── _pagina_capa_e_sintese()      ← capa + tabela ident + KPIs
        ├── _pagina_achados_criticos()    ← C-01, C-10, C-03...
        ├── _pagina_achados_medios()      ← M-01, M-02, AT-01
        ├── _pagina_planilha_gado_ir()    ← vendas/remessas/compras + F1-F6
        └── _pagina_plano_acao() ...      ← (só modo "completo")

Uso (executar):
    python scripts/modelo_pdf_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.services.auditoria_cruzada_pdf import gerar_pdf_auditoria_cruzada


# ═══════════════════════════════════════════════════════════════════════════
#  PAYLOAD DEMO — schema mínimo aceito pelo motor (modo="simplificado")
# ═══════════════════════════════════════════════════════════════════════════

PAYLOAD_DEMO = {
    # ── Identificação ────────────────────────────────────────────────────
    "contribuinte": {
        "nome":      "CONTRIBUINTE EXEMPLO DE DEMONSTRAÇÃO",
        "cpf":       "000.000.000-00",
        "ie":        "000000000",
        "municipio": "MUNICÍPIO EXEMPLO",
        "estado":    "GO",
    },
    "periodo": {
        "inicio":          "2025-01-01",
        "fim":             "2025-12-31",
        "documento_base":  "Relatório GIEF/SEFAZ-GO de DD/MM/AAAA",
    },

    # ── Regra de classificação aplicada ───────────────────────────────────
    "regra_classificacao": "Classificação por NATUREZA do PDF GIEF (estado GO)",

    # ── Síntese quantitativa (modo GIEF-only) ─────────────────────────────
    "sintese_gief": [
        {"indicador": "Volume bruto total",
         "valor_pdf_gief": "R$ 1.000.000,00", "status": "—"},
        {"indicador": "Receita imediata (vendas)",
         "valor_pdf_gief": "R$ 700.000,00", "status": "—"},
        {"indicador": "Trânsito (remessas para leilão)",
         "valor_pdf_gief": "R$ 300.000,00", "status": "—"},
        {"indicador": "Cabeças totais movimentadas",
         "valor_pdf_gief": "350", "status": "—"},
        {"indicador": "Qtd notas de venda",
         "valor_pdf_gief": "40", "status": "—"},
        {"indicador": "Qtd notas de remessa",
         "valor_pdf_gief": "10", "status": "—"},
        {"indicador": "Qtd notas de compra",
         "valor_pdf_gief": "8", "status": "—"},
        {"indicador": "Valor total de compras",
         "valor_pdf_gief": "R$ 500.000,00", "status": "—"},
    ],

    # ── Mapa de severidades (totais por cor) ──────────────────────────────
    "severidades": {
        "CRITICO": 1,
        "ALTO":    1,
        "MEDIO":   2,
        "ATENCAO": 1,
        "CONFORME": 0,
    },

    # ── Indicadores principais (cards F1-F6) ──────────────────────────────
    "indicadores_principais": {
        "VOLUME_BRUTO":         {"valor": "1000000.00", "rotulo": "Volume Bruto",
                                  "subtitulo": "Vendas + Remessas"},
        "F1_RECEITA_IMEDIATA":  {"valor": "700000.00",  "rotulo": "F1 Receita Imediata",
                                  "subtitulo": "Vendas diretas"},
        "F2_TRANSITO":          {"valor": "300000.00",  "rotulo": "F2 Trânsito",
                                  "subtitulo": "Remessas a leilão"},
        "F6_COMPRAS":           {"valor": "500000.00",  "rotulo": "F6 Compras (RE-1)",
                                  "subtitulo": "Despesa/Investimento"},
        "F4_RECEITA_BRUTA":     {"valor": "700000.00",  "rotulo": "F4 Receita Bruta",
                                  "subtitulo": "DIRPF Rural"},
        "F5_RESULTADO_RURAL":   {"valor": "200000.00",  "rotulo": "F5 Resultado",
                                  "subtitulo": "F4 − F6"},
        "IRPF_ESTIMADO":        {"valor": "55000.00",   "rotulo": "IRPF Estimado",
                                  "subtitulo": "27,5% s/ F5"},
        "FUNRURAL":             {"valor": "10500.00",   "rotulo": "Funrural",
                                  "subtitulo": "1,50% s/ F1"},
    },

    # ── Achados CRÍTICOS (cada um vira um card vermelho com tabela) ──────
    "achados_criticos": [
        {
            "codigo":      "C-01",
            "titulo":      "Operação singular de valor extraordinário",
            "descricao":   ("NFA-e nº 99.999.999 concentra 25% da receita anual em "
                             "uma única operação. Volume desta magnitude requer "
                             "comprovação documental (extrato + GTA)."),
            "severidade":  "CRITICO",
            "porque_critico": ("Concentração atípica em operação singular "
                                "caracteriza descapitalização de plantel."),
            "cruzamentos": [
                "GTA AGRODEFESA-GO da nota",
                "Extrato bancário casado com o valor",
                "Capacidade do imóvel rural do destinatário (SiCAR/CAR)",
            ],
            "tabela_cabecalhos": ["NFA-e", "Data", "Cab.", "Valor", "% receita",
                                    "Destinatário", "CPF"],
            "tabela_linhas": [[
                "99.999.999", "31/05/2025", "100", "R$ 175.000,00", "25,00%",
                "DESTINATÁRIO EXEMPLO", "111.111.111-11",
            ]],
            "tabela_totais": [],
        },
    ],

    # ── Achados de criticidade MÉDIA (M-01 LCDPR + M-02 Funrural) ────────
    "achados_medios": [
        {
            "codigo":      "M-01",
            "titulo":      "Obrigações acessórias derivadas do volume",
            "descricao":   ("Volume bruto de R$ 1.000.000,00 obriga manutenção "
                             "do LCDPR (IN RFB 1.848/2018)."),
            "severidade":  "MEDIO",
            "porque_critico": ("Ausência do LCDPR sujeita o contribuinte a "
                                "multa de 0,25%/mês (art. 8º-A Lei 9.430/96)."),
            "cruzamentos": [],
            "tabela_cabecalhos": [],
            "tabela_linhas": [],
            "tabela_totais": [],
        },
        {
            "codigo":      "M-02",
            "titulo":      "Funrural a recolher",
            "descricao":   ("Funrural sobre R$ 700.000,00 à alíquota 1,50% "
                             "(PF Patronal): R$ 10.500,00."),
            "severidade":  "MEDIO",
            "porque_critico": "Base legal: Lei 8.212/91.",
            "cruzamentos": [
                "Guias GPS/DARF recolhidas no período",
                "Retenções por adquirente PJ (se aplicável)",
            ],
            "tabela_cabecalhos": [],
            "tabela_linhas": [],
            "tabela_totais": [],
        },
    ],

    # ── Pontos de ATENÇÃO ────────────────────────────────────────────────
    "pontos_atencao": [
        {
            "codigo":      "AT-01",
            "titulo":      "Compras de gado relevantes — Regra Especial 1 aplicada",
            "descricao":   ("R$ 500.000,00 em 8 notas de compra. Sob RE-1, reduz "
                             "base IRPF Rural ou ativa investimento dedutível."),
            "severidade":  "ATENCAO",
            "porque_critico": ("RE-1 reclassifica VENDA → COMPRA quando "
                                "contribuinte é DESTINATÁRIO."),
            "cruzamentos": [
                "GTA AGRODEFESA-GO de cada nota de compra",
                "Extrato bancário (PIX/débito) casado",
            ],
            "tabela_cabecalhos": [],
            "tabela_linhas": [],
            "tabela_totais": [],
        },
    ],

    # ── Plano de ação 30/60/90 (só renderiza em modo "completo") ─────────
    "etapas_recomendacoes": [
        {"numero": "1", "titulo": "Aprofundar achados críticos",
         "prazo": "30 dias", "accent": "#B91C1C",
         "itens": ["Solicitar GTAs", "Cruzar extratos bancários"]},
        {"numero": "2", "titulo": "Conformidade fiscal",
         "prazo": "60 dias", "accent": "#B45309",
         "itens": ["Reconstituir LCDPR 2025"]},
        {"numero": "3", "titulo": "Mitigação prospectiva",
         "prazo": "90 dias", "accent": "#1D4ED8",
         "itens": ["Adequar à Reforma Tributária (LC 214/2025)"]},
    ],

    # ── Planilha de Gado IR (sempre renderiza se presente) ───────────────
    "planilha_gado_ir": {
        "vendas": [
            {"mes": "Janeiro",  "qtd_notas": 5,  "cabecas": 30, "valor": "100000.00"},
            {"mes": "Junho",    "qtd_notas": 10, "cabecas": 60, "valor": "200000.00"},
            {"mes": "Outubro",  "qtd_notas": 15, "cabecas": 90, "valor": "300000.00"},
            {"mes": "Dezembro", "qtd_notas": 10, "cabecas": 70, "valor": "100000.00"},
        ],
        "remessas": [
            {"mes": "Março",  "qtd_notas": 3, "cabecas": 30, "valor": "100000.00"},
            {"mes": "Agosto", "qtd_notas": 7, "cabecas": 80, "valor": "200000.00"},
        ],
        "compras": [
            {"mes": "Fevereiro", "qtd_notas": 3, "cabecas": 80,  "valor": "200000.00"},
            {"mes": "Setembro",  "qtd_notas": 5, "cabecas": 120, "valor": "300000.00"},
        ],
        "totais": {
            "vendas":   {"qtd_notas": 40, "cabecas": 250, "valor": "700000.00"},
            "remessas": {"qtd_notas": 10, "cabecas": 110, "valor": "300000.00"},
            "compras":  {"qtd_notas": 8,  "cabecas": 200, "valor": "500000.00"},
        },
        "formula_regra_2": {
            "F1": {"descricao": "Receita imediata (vendas diretas)",
                    "valor": "700000.00"},
            "F2": {"descricao": "Trânsito potencial (remessas — NÃO base IRPF)",
                    "valor": "300000.00"},
            "F3": {"descricao": "Receita realizada de leilão (NF-e mod. 55)",
                    "valor": "0.00"},
            "F4": {"descricao": "Receita bruta total DIRPF Rural (F1 + F3)",
                    "valor": "700000.00"},
            "F6": {"descricao": "Despesa / Investimento dedutível (compras)",
                    "valor": "500000.00"},
            "F5": {"descricao": "Resultado da atividade rural (F4 − F6)",
                    "valor": "200000.00"},
        },
    },

    # ── Rodapé técnico ───────────────────────────────────────────────────
    "declaracao_alcance": (
        "Este relatório foi produzido com base no PDF GIEF/SEFAZ-GO e na "
        "Planilha de Gado para IR v5 do sistema OrgAudi 1.1. Os achados "
        "constituem indícios objetivos derivados de cruzamentos lógicos "
        "internos, não confirmados com documentação primária externa."),
    "sistema":      "OrgAudi 1.1",
    "audit_hash":   "0" * 64,
    "payload_hash": "{}",
    "timestamp":    "2026-05-18T00:00:00",
}


def main() -> None:
    saida = RAIZ / "reports_nfa" / "MODELO_DEMO_simplificado.pdf"
    saida.parent.mkdir(parents=True, exist_ok=True)

    print("Gerando PDF modelo (modo=simplificado) ...")
    pdf_bytes = gerar_pdf_auditoria_cruzada(PAYLOAD_DEMO, modo="simplificado")
    saida.write_bytes(pdf_bytes)
    print(f"[OK] {saida} ({len(pdf_bytes)/1024:.1f} KB)")

    print("\nGerando PDF modelo (modo=completo) ...")
    saida_full = saida.with_name("MODELO_DEMO_completo.pdf")
    pdf_full = gerar_pdf_auditoria_cruzada(PAYLOAD_DEMO, modo="completo")
    saida_full.write_bytes(pdf_full)
    print(f"[OK] {saida_full} ({len(pdf_full)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
