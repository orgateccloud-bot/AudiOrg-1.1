"""scripts/gerar_modelos_schema.py
═══════════════════════════════════════════════════════════════════════════
Gera os dois MODELOS JSON canônicos da auditoria OrgAudi 1.1 (schema
auditoria_v2 + auditoria_cruzada), enriquecidos com exemplos de TODOS os
achados endurecidos T-01..T-08 + AN-01..AN-17.

Saída:
    docs/schemas/auditoria_cruzada_v2.json    — 16 chaves (simplificado)
    docs/schemas/auditoria_cruzada.json       — 21 chaves (completo)

Os arquivos servem como REFERÊNCIA estrutural — todos os campos com valores
neutros (CONTRIBUINTE EXEMPLO, CPF 000.000.000-00, valores ilustrativos).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
DEST = RAIZ / "docs" / "schemas"
DEST.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
#  ACHADOS ENDURECIDOS — exemplos canônicos de cada detector
# ═══════════════════════════════════════════════════════════════════════════

ACHADOS_CRITICOS_ENDURECIDOS = [
    # ─── T-01 Concentração de nota individual ─────────────────────────────
    {
        "codigo": "C-T01",
        "titulo": "T-01 Concentração de nota individual — operação ≥ 7% da receita anual",
        "descricao": "Critério endurecido: nota individual ≥ 7% da receita anual = CRÍTICO; 3-7% = ATENÇÃO. Concentração atípica em evento único sinaliza AN-13 (concentração atípica) e indício de AN-18 (caixa dois) quando associada a contraparte recorrente.",
        "severidade": "CRITICO",
        "porque_critico": "Concentração em evento único pode mascarar AN-18 (caixa dois) quando associada a contraparte recorrente; magnitude exige comprovação de capacidade produtiva e fluxo financeiro.",
        "cruzamentos": [
            "GTA AGRODEFESA-GO de cada NFA-e listada",
            "Extrato bancário casado com os valores totais",
            "Capacidade do imóvel rural do destinatário (SiCAR/CAR)",
            "Vínculo familiar/societário (JUCEG/RFB) do destinatário"
        ],
        "tabela_cabecalhos": ["NFA-e", "Data", "Valor", "% receita",
                                "Destinatário", "CPF"],
        "tabela_linhas": [[
            "00000000", "DD/MM/AAAA", "R$ 0,00", "0,00%",
            "DESTINATARIO EXEMPLO", "000.000.000-00"
        ]],
        "tabela_totais": []
    },
    # ─── T-02 Smurfing 4 subtipos (AN-01) ─────────────────────────────────
    {
        "codigo": "C-T02",
        "titulo": "T-02 Smurfing / Fragmentação fiscal (AN-01) — 4 subtipos",
        "descricao": "Critérios endurecidos: A) 3+ notas idênticas mesmo dia | B) 4+ notas em 7d com 2+ valores iguais | C) 2+ notas mesma data + mesma contraparte | D) 3+ notas mesma contraparte em 30d, soma ≥ R$ 100k. Padrão AN-01 (Eixo I - Manipulação de Valores).",
        "severidade": "CRITICO",
        "porque_critico": "Hipóteses: (i) manter cada nota abaixo de limiar de triagem; (ii) uso de 'laranja'; (iii) lavagem de gado; (iv) elusão de regimes especiais.",
        "cruzamentos": [
            "GTAs AGRODEFESA-GO de todas as notas do dia/janela",
            "Extrato bancário do contribuinte (PIX/depósitos casados)",
            "CAEPF do destinatário recorrente",
            "Vínculo familiar/societário (JUCEG/RFB)"
        ],
        "tabela_cabecalhos": ["Sub", "Destinatário", "CPF", "Qtd",
                                "Valor total", "Janela"],
        "tabela_linhas": [
            ["A", "DESTINATARIO EXEMPLO", "000.000.000-00", "3",
             "R$ 0,00", "DD/MM/AAAA"],
            ["C", "DESTINATARIO EXEMPLO", "000.000.000-00", "2",
             "R$ 0,00", "DD/MM/AAAA"]
        ],
        "tabela_totais": []
    },
    # ─── T-03 Concentração de contraparte (AN-13) ─────────────────────────
    {
        "codigo": "C-T03",
        "titulo": "T-03 Captura monopsônica — TOP-1 ≥ 30% da receita",
        "descricao": "Critério: 1 contraparte ≥ 30% da receita = CRÍTICO; ≥ 20% = ATENÇÃO; TOP-3 ≥ 70% = CRÍTICO. Detecta AN-13 (concentração atípica) e indicia AN-05 (laranja) ou AN-07 (intermediação não declarada).",
        "severidade": "CRITICO",
        "porque_critico": "Captura monopsônica caracteriza dependência operacional do produtor face a 1 único comprador, padrão atípico em pecuária extensiva e sugestivo de venda casada/contratada.",
        "cruzamentos": [
            "CAEPF do destinatário concentrado",
            "Vínculo societário/familiar (JUCEG/RFB)",
            "Histórico bancário do destinatário",
            "Eventos de leilão registrados no exercício"
        ],
        "tabela_cabecalhos": ["#", "Destinatário", "CPF", "Qtd",
                                "Valor", "% receita"],
        "tabela_linhas": [
            ["1", "DESTINATARIO EXEMPLO", "000.000.000-00", "0",
             "R$ 0,00", "0,00%"]
        ],
        "tabela_totais": []
    },
    # ─── AN-02 Subfaturamento (Eixo I) ────────────────────────────────────
    {
        "codigo": "C-AN02",
        "titulo": "AN-02 Subfaturamento vs Pauta SEFAZ-GO (Eixo I)",
        "descricao": "R$/cabeça < R$ 1.000 = CRÍTICO; R$ 1.000-1.500 = ATENÇÃO. Pauta mínima SEFAZ-GO: R$ 1.385/cab (bezerra fêmea ≤ 12m).",
        "severidade": "CRITICO",
        "porque_critico": "Subfaturamento omite base de Funrural, IRPF Rural e reduz ICMS do estado-destino. Caracteriza dolo quando reiterado.",
        "cruzamentos": [
            "Pauta SEFAZ-GO vigente na data da operação",
            "GTA AGRODEFESA-GO (categoria/peso do animal)",
            "Extrato bancário (recebimento real vs declarado)"
        ],
        "tabela_cabecalhos": ["NFA-e", "Data", "R$/cab", "Cab",
                                "Valor", "Destinatário"],
        "tabela_linhas": [[
            "00000000", "DD/MM/AAAA", "R$ 0,00", "0",
            "R$ 0,00", "DESTINATARIO EXEMPLO"
        ]],
        "tabela_totais": []
    },
    # ─── AN-08 Transferência intrafamiliar (Eixo II) ──────────────────────
    {
        "codigo": "C-AN08",
        "titulo": "AN-08 Transferência intrafamiliar disfarçada de venda (Eixo II)",
        "descricao": "Destinatário compartilha sobrenome RARO com o contribuinte (SILVA/SANTOS excluídos por ultracomuns). Indica venda disfarçada entre familiares — burla potencial a ITCMD/ITBI.",
        "severidade": "CRITICO",
        "porque_critico": "Transferências familiares simuladas como venda burlam imposto sobre doação (ITCMD) e podem caracterizar planejamento abusivo.",
        "cruzamentos": [
            "Certidão de relacionamento (cartório/Receita)",
            "Extrato bancário (verificar pagamento real entre as partes)",
            "Imposto sobre doação (ITCMD) recolhido no exercício"
        ],
        "tabela_cabecalhos": ["Destinatário", "CPF", "Sobrenomes",
                                "Notas", "Valor"],
        "tabela_linhas": [[
            "DESTINATARIO EXEMPLO", "000.000.000-00", "SOBRENOME",
            "0", "R$ 0,00"
        ]],
        "tabela_totais": []
    },
    # ─── AN-17 Cascata inter-cliente (Eixo V) ─────────────────────────────
    {
        "codigo": "C-AN17",
        "titulo": "AN-17 Emissão em cascata A→B→C (Eixo V)",
        "descricao": "Gado deste cliente (A) foi vendido a outro cliente da carteira (B) e revendido a um terceiro (C) dentro de 60 dias. Identifica B como possível trader intermediário (não produtor rural real). Padrão Eixo V — esquema estruturado de circulação de gado.",
        "severidade": "CRITICO",
        "porque_critico": "Cascatas A→B→C de curta duração caracterizam B como interposta pessoa (AN-05) ou intermediário não declarado (AN-07), gerando créditos fictícios de Funrural e elusão de IRPF Rural.",
        "cruzamentos": [
            "GTA AGRODEFESA-GO (rastrear identificação do gado entre as 3 partes)",
            "CAEPF do cliente B (atividade rural real?)",
            "Extrato bancário do cliente B (margem real da operação)",
            "Notas de despesa de B no período (alimentação/manejo)"
        ],
        "tabela_cabecalhos": ["B (intermediário)", "C (final)",
                                "Data A→B", "Data B→C", "Dias"],
        "tabela_linhas": [[
            "CLIENTE_B_EXEMPLO", "CLIENTE_C_EXEMPLO",
            "DD/MM/AAAA", "DD/MM/AAAA", "0"
        ]],
        "tabela_totais": []
    }
]

ACHADOS_MEDIOS_ENDURECIDOS = [
    # ─── M-01 / M-02 preservados ──────────────────────────────────────────
    {
        "codigo": "M-01",
        "titulo": "Obrigações acessórias derivadas do volume",
        "descricao": "Volume bruto obriga manutenção do LCDPR (IN RFB 1.848/2018) e apuração no anexo da DIRPF Rural.",
        "severidade": "MEDIO",
        "porque_critico": "Ausência do LCDPR sujeita a multa de 0,25% por mês sobre a receita bruta rural (art. 8º-A Lei 9.430/96).",
        "cruzamentos": [],
        "tabela_cabecalhos": [],
        "tabela_linhas": [],
        "tabela_totais": []
    },
    {
        "codigo": "M-02",
        "titulo": "Funrural a recolher",
        "descricao": "Estimativa de Funrural sobre vendas diretas. Cruzar com guias GPS/DARF efetivamente recolhidas.",
        "severidade": "MEDIO",
        "porque_critico": "Base legal: Lei 8.212/91.",
        "cruzamentos": [
            "Conferir guias GPS/DARF recolhidas no período",
            "Para adquirentes PJ, validar retenção do comprador"
        ],
        "tabela_cabecalhos": [],
        "tabela_linhas": [],
        "tabela_totais": []
    },
    # ─── T-04 Concentração PF (sev ALTO se crítico) ──────────────────────
    {
        "codigo": "A-T04",
        "titulo": "T-04 Concentração em PFs com perfil de revenda",
        "descricao": "Critério endurecido: ≥ 85% das vendas para PF + recorrência (3+ aquisições) = CRÍTICO; ≥ 70% = ATENÇÃO. Indica AN-07 (intermediação não declarada) e potencial AN-05 (uso de laranjas).",
        "severidade": "ALTO",
        "porque_critico": "PF sem CAEPF + 3+ aquisições = intermediação não declarada (AN-07) ou potencial laranja (AN-05). Cada PF deve ter atividade rural declarada na RFB.",
        "cruzamentos": [
            "CAEPF de cada PF recorrente (Receita Federal)",
            "GTAs AGRODEFESA-GO em nome dos PFs",
            "Capacidade do imóvel rural (SiCAR) dos PFs"
        ],
        "tabela_cabecalhos": ["Destinatário PF", "CPF", "Notas", "Valor"],
        "tabela_linhas": [[
            "PF EXEMPLO", "000.000.000-00", "0", "R$ 0,00"
        ]],
        "tabela_totais": []
    },
    # ─── AN-11 Sazonalidade (Eixo III) ────────────────────────────────────
    {
        "codigo": "A-AN11",
        "titulo": "AN-11 Sazonalidade incompatível (Eixo III)",
        "descricao": "Ciclo pecuário tipicamente distribui receita ao longo de 6-9 meses. Concentração ≥50% em 1 mês = CRÍTICO; ≥30% = ATENÇÃO.",
        "severidade": "MEDIO",
        "porque_critico": "Concentração temporal isolada é incompatível com ciclo pecuário padrão e pode mascarar evento de descapitalização total do plantel.",
        "cruzamentos": [
            "Evolução mensal do estoque (LCDPR)",
            "GTAs AGRODEFESA-GO emitidas no mês",
            "Capacidade do imóvel rural ao longo do ano"
        ],
        "tabela_cabecalhos": ["Mês", "% receita", "Valor", "Qtd notas"],
        "tabela_linhas": [[
            "MMMM", "0,0%", "R$ 0,00", "0"
        ]],
        "tabela_totais": []
    }
]

PONTOS_ATENCAO_ENDURECIDOS = [
    {
        "codigo": "AT-01",
        "titulo": "Compras de gado relevantes — Regra Especial 1 aplicada",
        "descricao": "Notas de compra reduzem a base do IRPF Rural ou ativam investimento dedutível conforme finalidade (NBC TG 16 + Lei 9.250/1995).",
        "severidade": "ATENCAO",
        "porque_critico": "RE-1 reclassifica NFA-e com produtor como DESTINATÁRIO em atividade rural de VENDA → COMPRA. Confiança 0,99.",
        "cruzamentos": [
            "GTA AGRODEFESA correspondente a cada nota",
            "Extrato bancário (PIX/débito) casado com valores",
            "Decisão contábil (despesa imediata vs ativo amortizável)"
        ],
        "tabela_cabecalhos": [],
        "tabela_linhas": [],
        "tabela_totais": []
    },
    # ─── AN-14 Ciclo curto (Eixo IV) ──────────────────────────────────────
    {
        "codigo": "AT-AN14",
        "titulo": "AN-14 Ciclo operacional implausível (Eixo IV)",
        "descricao": "Compra (PDF DEST) e revenda (PDF REM) do mesmo lote em janela < 60 dias — incompatível com ciclo de recria/engorda. Indício de AN-17 (cascata) ou AN-16 (carrossel).",
        "severidade": "ATENCAO",
        "porque_critico": "Ciclo pecuário formal (recria 8-12m, engorda 4-6m) torna inviável valorização em <60d. Padrão típico de trader/intermediário não declarado.",
        "cruzamentos": [
            "GTA AGRODEFESA-GO entrada e saída (verificar mesma identificação)",
            "Notas de despesa (alimentação, manejo) no intervalo",
            "CAEPF do contribuinte (atividade pecuária real?)"
        ],
        "tabela_cabecalhos": ["Dias", "Compra (Remetente)",
                                "Venda (Destinatário)", "Cab", "Valor venda"],
        "tabela_linhas": [[
            "0", "DD/MM/AAAA · REMETENTE EXEMPLO",
            "DD/MM/AAAA · DESTINATARIO EXEMPLO", "0", "R$ 0,00"
        ]],
        "tabela_totais": []
    }
]


# ═══════════════════════════════════════════════════════════════════════════
#  ESTRUTURAS COMUNS
# ═══════════════════════════════════════════════════════════════════════════

CONTRIBUINTE = {
    "cpf": "000.000.000-00",
    "nome": "CONTRIBUINTE EXEMPLO",
    "ie": "",
    "municipio": "MUNICIPIO EXEMPLO",
    "estado": "GO"
}

PERIODO = {
    "inicio": "2025-01-01",
    "fim": "2025-12-31",
    "documento_base": "Relatório GIEF/SEFAZ de DD/MM/AAAA"
}

SINTESE_GIEF = [
    {"indicador": "Volume bruto total", "valor_pdf_gief": "R$ 1.000.000,00"},
    {"indicador": "Receita imediata (vendas)", "valor_pdf_gief": "R$ 700.000,00"},
    {"indicador": "Trânsito (remessas para leilão)", "valor_pdf_gief": "R$ 300.000,00"},
    {"indicador": "Cabeças totais movimentadas", "valor_pdf_gief": "500"},
    {"indicador": "Qtd notas de venda", "valor_pdf_gief": "50"},
    {"indicador": "Qtd notas de remessa", "valor_pdf_gief": "12"},
    {"indicador": "Qtd notas de compra", "valor_pdf_gief": "8"},
    {"indicador": "Valor total de compras", "valor_pdf_gief": "R$ 400.000,00"}
]

INDICADORES_PRINCIPAIS = {
    "VOLUME_BRUTO": {"valor": "1000000.00", "rotulo": "R$ 1,00M",
                      "subtitulo": "62 saídas",
                      "valor_completo": "R$ 1.000.000,00"},
    "F1_RECEITA_IMEDIATA": {"valor": "700000.00", "rotulo": "R$ 700K",
                              "subtitulo": "50 vendas · base IRPF",
                              "valor_completo": "R$ 700.000,00"},
    "F2_TRANSITO": {"valor": "300000.00", "rotulo": "R$ 300K",
                     "subtitulo": "12 remessas · não soma",
                     "valor_completo": "R$ 300.000,00"},
    "F6_COMPRAS": {"valor": "400000.00", "rotulo": "R$ 400K",
                    "subtitulo": "8 notas · despesa",
                    "valor_completo": "R$ 400.000,00"},
    "F4_RECEITA_BRUTA": {"valor": "700000.00", "rotulo": "R$ 700K",
                          "subtitulo": "F1 + F3",
                          "valor_completo": "R$ 700.000,00"},
    "F5_RESULTADO_RURAL": {"valor": "300000.00", "rotulo": "R$ 300K",
                            "subtitulo": "F4 − F6 · base IRPF",
                            "valor_completo": "R$ 300.000,00"},
    "IRPF_ESTIMADO": {"valor": "60000.00", "rotulo": "R$ 60K",
                       "subtitulo": "20% × F5 · Lei 8.023/90",
                       "valor_completo": "R$ 60.000,00"},
    "FUNRURAL": {"valor": "10500.00", "rotulo": "R$ 11K",
                  "subtitulo": "1,50% × F1 · PF Patronal",
                  "valor_completo": "R$ 10.500,00"}
}

ETAPAS = [
    {"numero": 1, "titulo": "Aprofundar achados críticos",
     "prazo": "30 DIAS", "accent": "CRITICO",
     "itens": ["Solicitar documentação primária dos achados endurecidos: GTAs, extratos, ACTs, NF-e dos leiloeiros.",
                "Cruzar com sistemas externos: AGRODEFESA, RFB (CAEPF), SiCAR, JUCEG.",
                "Verificar cascatas AN-17 inter-cliente da carteira (rede de relacionamentos)."]},
    {"numero": 2, "titulo": "Conformidade fiscal",
     "prazo": "60 DIAS", "accent": "ALTO",
     "itens": ["Reconstituir o LCDPR do período.",
                "Apurar o IRPF Rural (ano-base).",
                "Conferir Funrural recolhido contra a estimativa do relatório."]},
    {"numero": 3, "titulo": "Mitigação prospectiva",
     "prazo": "90 DIAS", "accent": "MEDIO",
     "itens": ["Implantar segregação de fluxos nos sistemas internos.",
                "Adequar à Reforma Tributária (LC 214/2025) — CBS/IBS a partir de 2027."]}
]

PLANILHA_GADO_IR = {
    "vendas": [],
    "remessas": [],
    "compras": [],
    "totais": {
        "vendas": {"qtd_notas": 50, "cabecas": 0, "valor": "700000.00"},
        "remessas": {"qtd_notas": 12, "cabecas": 0, "valor": "300000.00"},
        "compras": {"qtd_notas": 8, "cabecas": 0, "valor": "400000.00"},
        "saidas_consolidadas": {"qtd_notas": 62, "cabecas": 0, "valor": "1000000.00"}
    },
    "formula_regra_2": {
        "F1": {"descricao": "Receita imediata (vendas diretas)",
                "valor": "700000.00"},
        "F2": {"descricao": "Trânsito potencial (remessas — NÃO base IRPF)",
                "valor": "300000.00"},
        "F3": {"descricao": "Receita realizada de leilão (NF-e mod. 55)",
                "valor": "0"},
        "F4": {"descricao": "Receita bruta total DIRPF Rural (F1 + F3)",
                "valor": "700000.00"},
        "F6": {"descricao": "Despesa / Investimento dedutível (compras)",
                "valor": "400000.00"},
        "F5": {"descricao": "Resultado da atividade rural (F4 − F6)",
                "valor": "300000.00"}
    }
}

DECLARACAO = (
    "Este relatório foi produzido com base no PDF GIEF/SEFAZ pelo sistema "
    "OrgAudi 1.1. A classificação das operações segue a regra NATUREZA do "
    "GIEF (estado GO) ou CFOP (demais estados). Os achados constituem "
    "indícios objetivos derivados de cruzamentos lógicos internos "
    "(bateria endurecida T-01..T-08 + catálogo AN-01..AN-18), não "
    "confirmados com documentação primária externa (extratos bancários, "
    "GTAs, ACTs, contratos). A confirmação depende de etapa subsequente.\n\n"
    "O presente documento NÃO formula acusações, NÃO imputa dolo e NÃO "
    "substitui procedimento de fiscalização tributária formal."
)

# ═══════════════════════════════════════════════════════════════════════════
#  CHAVES EXCLUSIVAS DO MODO COMPLETO (17-21)
# ═══════════════════════════════════════════════════════════════════════════

EIXOS_TIPOLOGIAS = {
    "I": "Manipulação de Valores",
    "II": "Irregularidade das Partes",
    "III": "Irregularidade da Mercadoria",
    "IV": "Irregularidade Cadastral e Operacional",
    "V": "Esquemas Estruturados"
}

TIPOLOGIAS_CONSIDERADAS = [
    "Fragmentação fiscal (smurfing)",
    "Subfaturamento vs pauta SEFAZ",
    "Superfaturamento reverso de compras",
    "Uso de laranjas / interpostas pessoas",
    "Destinatário fantasma",
    "Intermediação não declarada",
    "Transferência intrafamiliar disfarçada",
    "Concentração atípica de contraparte",
    "Sazonalidade incompatível",
    "Ciclo operacional implausível",
    "Emissão em cascata"
]

CATALOGO_ANOMALIAS = [
    {"codigo": "AN-01", "eixo": "I", "tipo": "Smurfing",
     "descricao": "Fragmentação de lotes grandes em múltiplas notas pequenas",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural", "ICMS"]},
    {"codigo": "AN-02", "eixo": "I", "tipo": "Subfaturamento",
     "descricao": "Valor declarado abaixo da pauta SEFAZ-GO",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural", "ICMS"]},
    {"codigo": "AN-03", "eixo": "I", "tipo": "Superfaturamento reverso",
     "descricao": "Inflação de despesas via compra superfaturada",
     "gravidade": "ALTO", "tributos": ["IRPF"]},
    {"codigo": "AN-04", "eixo": "I", "tipo": "Subdeclaração em leilão",
     "descricao": "Conluio com leiloeiro para não emitir NF-e de arremate",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural"]},
    {"codigo": "AN-05", "eixo": "II", "tipo": "Laranjas",
     "descricao": "Uso de interpostas pessoas sem atividade rural real",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural"]},
    {"codigo": "AN-06", "eixo": "II", "tipo": "Destinatário fantasma",
     "descricao": "CPF/CNPJ inexistente ou inativo no momento da operação",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural", "ICMS"]},
    {"codigo": "AN-07", "eixo": "II", "tipo": "Intermediação não declarada",
     "descricao": "PF comprando para revender sem emitir nota",
     "gravidade": "ALTO", "tributos": ["IRPF", "Funrural"]},
    {"codigo": "AN-08", "eixo": "II", "tipo": "Transferência intrafamiliar",
     "descricao": "Transferência disfarçada de venda, burlando ITCMD e ITBI",
     "gravidade": "ALTO", "tributos": ["ITCMD", "ITBI"]},
    {"codigo": "AN-09", "eixo": "III", "tipo": "Lavagem de origem de gado",
     "descricao": "Uso de NFA-e para 'limpar' gado sem procedência",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural", "ICMS"]},
    {"codigo": "AN-10", "eixo": "III", "tipo": "Capacidade produtiva incompatível",
     "descricao": "Volume vendido impossível para a área do SiCAR",
     "gravidade": "CRITICO", "tributos": ["IRPF"]},
    {"codigo": "AN-11", "eixo": "III", "tipo": "Sazonalidade incompatível",
     "descricao": "Sazonalidade incompatível com o ciclo pecuário",
     "gravidade": "MEDIO", "tributos": ["IRPF"]},
    {"codigo": "AN-12", "eixo": "IV", "tipo": "Inconsistência cadastral",
     "descricao": "IE inativa, CAEPF encerrado, CNPJ baixado",
     "gravidade": "ALTO", "tributos": ["ICMS", "Funrural"]},
    {"codigo": "AN-13", "eixo": "IV", "tipo": "Concentração atípica",
     "descricao": "Poucos compradores absorvendo volume desproporcional",
     "gravidade": "ALTO", "tributos": ["IRPF", "Funrural"]},
    {"codigo": "AN-14", "eixo": "IV", "tipo": "Ciclo operacional implausível",
     "descricao": "Compra e venda do mesmo lote em janela curta demais",
     "gravidade": "ATENCAO", "tributos": ["IRPF"]},
    {"codigo": "AN-15", "eixo": "IV", "tipo": "Endereço fiscal fantasma",
     "descricao": "Propriedade não localizada no SiCAR",
     "gravidade": "ALTO", "tributos": ["IRPF", "ICMS"]},
    {"codigo": "AN-16", "eixo": "V", "tipo": "Carrossel fiscal",
     "descricao": "Gado circula entre produtores gerando créditos fictícios",
     "gravidade": "CRITICO", "tributos": ["Funrural", "ICMS"]},
    {"codigo": "AN-17", "eixo": "V", "tipo": "Emissão em cascata",
     "descricao": "Cadeia produtor → intermediário → frigorífico sem trânsito real",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural", "ICMS"]},
    {"codigo": "AN-18", "eixo": "V", "tipo": "Caixa dois agropecuário",
     "descricao": "Receitas declaradas abaixo do real, diferença em espécie",
     "gravidade": "CRITICO", "tributos": ["IRPF", "Funrural", "ICMS"]}
]

REGRA_ESPECIAL_1 = {
    "titulo": "Regra Especial 1 (RE-1) — Cliente como DESTINATÁRIO → COMPRA",
    "aprovada_por": "ORGATEC AUDITORIA",
    "versao": "1.1",
    "definicao": "NFA-e com produtor rural como DESTINATÁRIO em atividade rural são reclassificadas de VENDA → COMPRA. Animal vivo é INSUMO/MATÉRIA-PRIMA, não receita. Conta débito 1.1.2.01 (Gado em Rebanho); conta crédito 2.1.1.1.01 (Fornecedores). Base legal: NBC TG 16 + NBC TG 25 + Lei 9.250/1995.",
    "criterios_primarios": [
        "Contribuinte aparece como DESTINATÁRIO na NFA-e",
        "Atividade rural declarada (CAEPF ou DIRPF Rural)",
        "Produto compatível (animal vivo, insumo agropecuário)",
        "Confiança 0,99 — validação secundária para valores extremos"
    ]
}

REGRA_5_CRUZAMENTOS = [
    {"fonte": "AGRODEFESA-GO",
     "o_que_confirmar": "GTAs emitidas correspondem às NFA-e do exercício",
     "como_cruzar": "Consultar sistema AGRODEFESA por CPF/CNPJ do produtor"},
    {"fonte": "Receita Federal (RFB)",
     "o_que_confirmar": "CAEPF ativo e atividade rural declarada",
     "como_cruzar": "Consulta CAEPF + DIRPF Rural"},
    {"fonte": "Junta Comercial (JUCEG)",
     "o_que_confirmar": "Vínculos societários do destinatário/contraparte",
     "como_cruzar": "Consulta de QSA via JUCEG"},
    {"fonte": "SiCAR / CAR",
     "o_que_confirmar": "Capacidade do imóvel rural (área, módulos fiscais)",
     "como_cruzar": "Validar volume de gado vs área declarada no CAR"},
    {"fonte": "Sistema bancário (BACEN)",
     "o_que_confirmar": "Fluxo financeiro casado com as notas",
     "como_cruzar": "Extratos bancários × valores das NFA-e"}
]


# ═══════════════════════════════════════════════════════════════════════════
#  MONTAGEM DOS 2 MODELOS
# ═══════════════════════════════════════════════════════════════════════════

def montar_modelo_v2() -> dict:
    """Modelo SIMPLIFICADO — 16 chaves de nível superior."""
    return {
        "contribuinte": CONTRIBUINTE,
        "periodo": PERIODO,
        "regra_classificacao": "NATUREZA_GIEF",
        "sintese_gief": SINTESE_GIEF,
        "severidades": {
            "CRITICO": 6, "ALTO": 1, "MEDIO": 3, "ATENCAO": 2, "CONFORME": 0
        },
        "indicadores_principais": INDICADORES_PRINCIPAIS,
        "achados_criticos": ACHADOS_CRITICOS_ENDURECIDOS,
        "achados_medios": ACHADOS_MEDIOS_ENDURECIDOS,
        "pontos_atencao": PONTOS_ATENCAO_ENDURECIDOS,
        "etapas_recomendacoes": ETAPAS,
        "declaracao_alcance": DECLARACAO,
        "audit_hash": "0" * 64,
        "sistema": "OrgAudi 1.1 — Bateria endurecida T-01..T-08 + AN-01..AN-17",
        "timestamp": "2026-01-01T00:00:00.000000+00:00",
        "payload_hash": "",
        "planilha_gado_ir": PLANILHA_GADO_IR
    }


def montar_modelo_completo() -> dict:
    """Modelo COMPLETO — 21 chaves (16 do v2 + 5 catálogos)."""
    m = montar_modelo_v2()
    m["tipologias_consideradas"] = TIPOLOGIAS_CONSIDERADAS
    m["regra_especial_1"] = REGRA_ESPECIAL_1
    m["regra_5_cruzamentos_externos"] = REGRA_5_CRUZAMENTOS
    m["catalogo_anomalias"] = CATALOGO_ANOMALIAS
    m["eixos_tipologias"] = EIXOS_TIPOLOGIAS
    return m


def main() -> None:
    v2 = montar_modelo_v2()
    completo = montar_modelo_completo()

    arq_v2 = DEST / "auditoria_cruzada_v2.json"
    arq_v2.write_text(json.dumps(v2, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"[OK] {arq_v2} — {len(v2)} chaves")

    arq_full = DEST / "auditoria_cruzada.json"
    arq_full.write_text(json.dumps(completo, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print(f"[OK] {arq_full} — {len(completo)} chaves")

    # Validação cruzada — gera PDF a partir do modelo
    print("\nValidando produção de PDF a partir dos modelos...")
    sys.path.insert(0, str(RAIZ))
    from api.services.auditoria_cruzada_pdf import gerar_pdf_auditoria_cruzada
    for arq, modo in [(arq_v2, "simplificado"), (arq_full, "completo")]:
        d = json.loads(arq.read_text(encoding="utf-8"))
        pdf = gerar_pdf_auditoria_cruzada(d, modo=modo)
        print(f"  {arq.name:40s} → {modo:13s} {len(pdf)/1024:.1f} KB")


if __name__ == "__main__":
    main()
