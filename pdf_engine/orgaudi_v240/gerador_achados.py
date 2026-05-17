"""
orgaudi.gerador_achados
═══════════════════════
Gerador de Achados estruturados e blocos textuais do relatório de auditoria
conforme o modelo ORGATEC (AUDITORIA_CRUZADA_GENIS_2025_v1_1.pdf).

Produz:
  • M-01 LCDPR — Livro Caixa Digital obrigatório quando o volume bruto da
    atividade rural ultrapassa o limite legal de R$ 4.800,00 (IN RFB
    1.848/2018 — Capítulo VI, Seção III).
  • M-02 Funrural a recolher — sempre que houver receita imediata, gera
    achado MÉDIO com valor estimado calculado pelo ResumoFiscal.
  • Plano de Ação em 3 etapas (30/60/90 dias).
  • Tabela "Cruzamentos com Bases Externas" (Regra 5 do modelo).
  • Declaração de Alcance e Limitações (com referência ao art. 138 CTN).

Cada bloco é uma constante de texto OU um construtor que recebe o
`ResumoFiscal` e devolve `Achado`/`Etapa`. Nenhum tem efeito colateral —
serve para alimentar o `pages.py` na renderização do PDF e também a rota
HTTP `/auditoria/cruzada` para inclusão na resposta JSON.
"""
from __future__ import annotations

from decimal import Decimal

from .data_processing import ResumoFiscal
from .domain import Achado, Etapa, Severidade


# Limite legal para obrigatoriedade do LCDPR (IN RFB 1.848/2018)
LIMITE_LCDPR = Decimal("4800.00")


def _fmt_brl(valor: Decimal) -> str:
    """Formata Decimal em pt-BR sem prefixo R$ — só o número (1.234.567,89)."""
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    s = f"{valor:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ═══════════════════════════════════════════════════════════════════════════
#  ACHADOS DE CRITICIDADE MÉDIA — M-01 (LCDPR) e M-02 (Funrural)
# ═══════════════════════════════════════════════════════════════════════════

def gerar_achado_m01_lcdpr(resumo: ResumoFiscal) -> Achado | None:
    """M-01 — Obrigatoriedade do LCDPR derivada do volume.

    A IN RFB 1.848/2018 torna obrigatória a manutenção do Livro Caixa Digital
    do Produtor Rural (LCDPR) quando a receita bruta da atividade rural no
    ano-calendário ultrapassar R$ 4.800,00. Acima desse limite, o achado
    sempre é emitido com criticidade MÉDIA — não como falta, e sim como
    lembrete de obrigação acessória.
    """
    volume = resumo.valor_bruto_saidas + resumo.F3_receita_realizada_leilao
    if volume < LIMITE_LCDPR:
        return None

    return Achado(
        codigo="M-01",
        titulo="Obrigações acessórias derivadas do volume",
        descricao=(
            f"Volume bruto de R$ {_fmt_brl(volume)} obriga, para a DIRPF Rural: "
            f"(a) manutenção do LCDPR — Livro Caixa Digital do Produtor Rural "
            f"(IN RFB 1.848/2018); (b) apuração do resultado da atividade "
            f"rural no anexo correspondente da DIRPF; (c) controle de "
            f"comprovantes para contraprova fiscal (5 anos de retenção)."
        ),
        severidade=Severidade.MEDIO,
        porque_critico=(
            "Ausência do LCDPR sujeita o contribuinte a multa de 0,25% por "
            "mês-calendário ou fração, sobre o total da receita bruta da "
            "atividade rural (limite de 10%) — art. 8º-A da Lei 9.430/96."
        ),
    )


def gerar_achado_m02_funrural(resumo: ResumoFiscal) -> Achado | None:
    """M-02 — Funrural a recolher/conferir.

    Gera achado MÉDIO sempre que houver receita imediata. O valor estimado
    vem direto do `ResumoFiscal.funrural` (alíquota vigente determinada por
    categoria previdenciária e data de referência via LC 224/2025).
    """
    if resumo.F1_receita_imediata <= Decimal("0"):
        return None

    aliq_pct = resumo.aliquota_funrural_pct
    base_legal = resumo.base_legal_funrural
    valor_funrural = resumo.funrural
    receita = resumo.F1_receita_imediata

    descricao = (
        f"Funrural sobre vendas diretas (R$ {_fmt_brl(receita)}) à alíquota "
        f"de {aliq_pct} ({resumo.categoria_previdenciaria}): "
        f"R$ {_fmt_brl(valor_funrural)}. Cruzar com guias GPS/DARF "
        f"efetivamente recolhidas — quando adquirente é PJ, retenção é dele; "
        f"quando PF, do próprio produtor. As remessas a leilão gerarão "
        f"Funrural adicional pela responsabilidade do leiloeiro."
    )

    return Achado(
        codigo="M-02",
        titulo="Funrural a recolher",
        descricao=descricao,
        severidade=Severidade.MEDIO,
        porque_critico=f"Base legal: {base_legal}.",
        cruzamentos=[
            "Conferir guias GPS/DARF recolhidas no período contra a estimativa.",
            "Para adquirentes PJ, validar retenção realizada pelo comprador.",
            "Para leilões, validar repasse do Funrural pelo leiloeiro (ACT).",
        ],
    )


def gerar_achados_medios(resumo: ResumoFiscal) -> list[Achado]:
    """Conveniência: agrega M-01 e M-02 em uma lista (ignorando os None)."""
    return [a for a in (gerar_achado_m01_lcdpr(resumo),
                        gerar_achado_m02_funrural(resumo)) if a is not None]


# ═══════════════════════════════════════════════════════════════════════════
#  AT-01 — Ponto de Atenção sobre tratamento contábil das compras (RE-1)
# ═══════════════════════════════════════════════════════════════════════════

def gerar_achado_at01_compras_relevantes(resumo: ResumoFiscal,
                                          qtd_compras: int = 0) -> Achado | None:
    """AT-01 — Compras de gado relevantes: verificar tratamento contábil
    sob a Regra Especial 1 (RE-1) OrgAudi 1.1.

    A RE-1 reclassifica natureza-exibição VENDA → COMPRA quando, em uma
    NFA-e (SEFAZ-GO/GIEF), o contribuinte é DESTINATÁRIO e a atividade
    declarada é rural (cria, recria, engorda, criação, agricultura). Resultado:

      Natureza exibição → COMPRA
      Categoria contábil → DESPESA
      Efeito IRPF       → SUBTRAI (reduz base de cálculo)
      Débito             → 1.1.2.01  (Gado em Rebanho — Ativo Circulante)
      Crédito            → 2.1.1.1.01 (Fornecedores — Passivo Circulante)
      Confiança          → 0,99

    Base legal: NBC TG 16 (Estoques) + NBC TG 25 (Estimativas) + Lei
    9.250/1995 (IRPF PF Rural).
    """
    if resumo.F6_despesa <= Decimal("0"):
        return None

    return Achado(
        codigo="AT-01",
        titulo="Compras de gado relevantes — Regra Especial 1 aplicada",
        descricao=(
            f"R$ {_fmt_brl(resumo.F6_despesa)} em "
            f"{qtd_compras or resumo.qtd_compras} notas de compra. Sob a "
            f"Regra 1 OrgAudi 1.1 (Cliente=Destinatário → "
            f"DESPESA/INVEST.), reduz a base de cálculo do IRPF Rural ou "
            f"ativa investimento dedutível, conforme finalidade: reposição "
            f"de plantel = despesa imediata; matriz reprodutora = ativo "
            f"amortizável ao longo da vida útil."
        ),
        severidade=Severidade.ATENCAO,
        porque_critico=(
            "Regra Especial 1 (RE-1) aplicada: NFA-e com contribuinte como "
            "DESTINATÁRIO em atividade rural são reclassificadas de "
            "VENDA → COMPRA. Animal vivo é INSUMO/MATÉRIA-PRIMA, não "
            "receita. Conta débito 1.1.2.01 (Gado em Rebanho); conta "
            "crédito 2.1.1.1.01 (Fornecedores). Confiança 0,99. "
            "Base legal: NBC TG 16 + NBC TG 25 + Lei 9.250/1995."
        ),
        cruzamentos=[
            "GTA AGRODEFESA-GO correspondente a cada nota de compra",
            "Extrato bancário (PIX/débito) casado com os valores das notas",
            "Decisão contábil (despesa imediata vs ativo amortizável) por "
            "finalidade declarada do gado adquirido",
            "Validação secundária: notas > R$ 500.000 → revisão manual "
            "(confiança reduzida para 0,75)",
            "Validação secundária: notas < R$ 100 → suspeita de teste "
            "(confiança reduzida para 0,75)",
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════
#  REGRA ESPECIAL 1 (RE-1) — bloco textual estruturado p/ renderização no PDF
# ═══════════════════════════════════════════════════════════════════════════

REGRA_ESPECIAL_1 = {
    "titulo": "Regra Especial 1 (RE-1) — Reclassificação VENDA → COMPRA",
    "aprovada_por": "Robson Alain Veloso (CRC TO-002032/O-5 T-GO)",
    "versao": "1.0 — 05/05/2026",
    "definicao": (
        "Em NFA-e (SEFAZ-GO/GIEF) com natureza_sefaz = 'VENDA' e contribuinte "
        "na posição de DESTINATÁRIO em atividade rural (cria, recria, "
        "engorda, criação, agricultura), a natureza-exibição é "
        "reclassificada para COMPRA. O animal vivo passa a ser tratado "
        "como INSUMO/MATÉRIA-PRIMA, não como receita."
    ),
    "criterios_primarios": [
        "Documento é NFA-e (GIEF SEFAZ-GO) — exclui NF-e, CT-e, RPA.",
        "Papel do produtor é DESTINATÁRIO (recebendo) — não REMETENTE.",
        "Natureza SEFAZ informada é 'VENDA' — não COMPRA, REMESSA, LEILÃO "
        "ou DEVOLUÇÃO.",
        "Tipo de atividade ∈ {cria, recria, engorda, criação, agricultura, "
        "bovino, suíno, ave, caprino, ovino, equino, piscicultura, "
        "apicultura, soja, milho, feijão, cana, café}.",
    ],
    "criterios_secundarios": [
        ("Valor > R$ 500.000", "Alerta — revisão manual obrigatória "
         "(confiança 0,75)"),
        ("Valor < R$ 100", "Alerta — suspeita de teste/erro de digitação "
         "(confiança 0,75)"),
        ("Atividade genérica", "Alerta — clarificação requerida "
         "(confiança 0,75)"),
        ("Fornecedor novo", "Alerta — primeira operação, validar "
         "autenticidade"),
        ("Devolução em 30 dias", "Alerta — padrão de carrossel fiscal?"),
    ],
    "lancamento_contabil": {
        "debito":  {"conta": "1.1.2.01",
                    "nome":  "Gado em Rebanho",
                    "tipo":  "ATIVO CIRCULANTE — Estoque de Animais Vivos"},
        "credito": {"conta": "2.1.1.1.01",
                    "nome":  "Fornecedores",
                    "tipo":  "PASSIVO CIRCULANTE — Obrigações (compra)"},
    },
    "efeitos": {
        "natureza_exibicao":  "COMPRA",
        "categoria_contabil": "DESPESA",
        "efeito_irpf":        "SUBTRAI (reduz base do IRPF PF)",
        "regra_aplicada":     "REGRA_ESPECIAL_1",
        "confianca":          "0,99",
    },
    "base_legal": [
        "NBC TG 1 — Estrutura Conceitual (receita vs despesa)",
        "NBC TG 16 — Estoques (animais vivos como estoque)",
        "NBC TG 25 — Estimativas Contábeis",
        "Lei 9.250/1995 — IRPF PF Rural (deduções de despesas)",
        "Lei 9.393/1996 — ITR (receitas e despesas de exploração rural)",
        "SEFAZ-GO — Portaria de NFA-e (GIEF) + Manual SPED",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
#  CATÁLOGO COMPLETO DE 18 TIPOLOGIAS DE ANOMALIA (5 eixos)
# ═══════════════════════════════════════════════════════════════════════════

CATALOGO_18_ANOMALIAS: list[dict] = [
    # ─── Eixo I — Manipulação de Valores ────────────────────────────────────
    {"codigo": "AN-01", "eixo": "I",
     "tipo": "Fragmentação fiscal (smurfing)",
     "descricao": "Divisão artificial de operações para fugir de limites de "
                  "notificação ou de faixas tributárias.",
     "gravidade": "Alta",
     "tributos": "ICMS, FUNRURAL, IRPF Rural"},
    {"codigo": "AN-02", "eixo": "I",
     "tipo": "Subfaturamento declarado",
     "descricao": "Valor de NF-e/NFA-e sistematicamente abaixo do preço de "
                  "mercado da commodity.",
     "gravidade": "Alta",
     "tributos": "ICMS, FUNRURAL, IRPF Rural"},
    {"codigo": "AN-03", "eixo": "I",
     "tipo": "Superfaturamento reverso",
     "descricao": "Entradas declaradas acima do valor real para inflar "
                  "créditos ou justificar saídas maiores.",
     "gravidade": "Alta",
     "tributos": "ICMS, PIS/COFINS"},
    {"codigo": "AN-04", "eixo": "I",
     "tipo": "Subdeclaração em leilão (conluio com leiloeiro)",
     "descricao": "Ajuste entre arrematante e leiloeiro para registrar "
                  "valor inferior ao efetivamente pago.",
     "gravidade": "Muito Alta",
     "tributos": "ITBI, ICMS, IRPF"},

    # ─── Eixo II — Irregularidade de Partes ─────────────────────────────────
    {"codigo": "AN-05", "eixo": "II",
     "tipo": "Uso de interpostas pessoas (laranjas)",
     "descricao": "CPF/CNPJ de terceiros utilizados para ocultar real "
                  "remetente, destinatário ou beneficiário.",
     "gravidade": "Muito Alta",
     "tributos": "ICMS, IRPF, FUNRURAL"},
    {"codigo": "AN-06", "eixo": "II",
     "tipo": "Destinatário inexistente ou inativo",
     "descricao": "Emissão de NFA-e para cadastro CPF/CNPJ cancelado, "
                  "suspenso ou sem atividade rural comprovável.",
     "gravidade": "Alta",
     "tributos": "ICMS"},
    {"codigo": "AN-07", "eixo": "II",
     "tipo": "Intermediação não declarada por PF",
     "descricao": "Pessoa física operando como trader/intermediário sem "
                  "inscrição estadual e sem emissão de documento fiscal próprio.",
     "gravidade": "Média",
     "tributos": "ICMS, IRPF, FUNRURAL"},
    {"codigo": "AN-08", "eixo": "II",
     "tipo": "Transferência intrafamiliar disfarçada de venda",
     "descricao": "Operação entre cônjuges, ascendentes/descendentes ou "
                  "sócios encoberta como negócio oneroso para justificar "
                  "movimentação patrimonial.",
     "gravidade": "Alta",
     "tributos": "ITCMD, IRPF, ITBI"},

    # ─── Eixo III — Irregularidade de Mercadoria ────────────────────────────
    {"codigo": "AN-09", "eixo": "III",
     "tipo": "Lavagem de origem de gado",
     "descricao": "Reintrodução de animais de procedência irregular (sem "
                  "GTA válida, SISBOV inconsistente ou área embargada) na "
                  "cadeia documental formal.",
     "gravidade": "Muito Alta",
     "tributos": "ICMS, FUNRURAL"},
    {"codigo": "AN-10", "eixo": "III",
     "tipo": "Inconsistência de capacidade produtiva",
     "descricao": "Volume ou peso declarado incompatível com área "
                  "explorada, módulos fiscais, plantel histórico ou "
                  "eficiência produtiva da atividade.",
     "gravidade": "Alta",
     "tributos": "FUNRURAL, ITR, IRPF Rural"},
    {"codigo": "AN-11", "eixo": "III",
     "tipo": "Sazonalidade incompatível",
     "descricao": "Picos de emissão em períodos fora da curva histórica do "
                  "produtor ou do ciclo biológico/agrícola da commodity.",
     "gravidade": "Média",
     "tributos": "ICMS, FUNRURAL"},

    # ─── Eixo IV — Irregularidade Cadastral e Operacional ───────────────────
    {"codigo": "AN-12", "eixo": "IV",
     "tipo": "Inconsistência cadastral",
     "descricao": "Divergência entre dados do CNPJ/CPF, inscrição estadual, "
                  "endereço fiscal, CAR/SNCR e dados da SEFAZ.",
     "gravidade": "Média",
     "tributos": "ICMS, ITR"},
    {"codigo": "AN-13", "eixo": "IV",
     "tipo": "Concentração atípica de operações",
     "descricao": "Volume de emissões concentrado em poucos destinatários, "
                  "datas ou valores-âncora sem justificativa econômica.",
     "gravidade": "Média",
     "tributos": "ICMS, FUNRURAL"},
    {"codigo": "AN-14", "eixo": "IV",
     "tipo": "Ciclo operacional implausível",
     "descricao": "Compra e revenda de gado/grãos em intervalo de tempo "
                  "inviável para engorda, beneficiamento ou logística.",
     "gravidade": "Alta",
     "tributos": "ICMS, FUNRURAL, IRPF Rural"},
    {"codigo": "AN-15", "eixo": "IV",
     "tipo": "Endereço fiscal fantasma",
     "descricao": "Imóvel rural declarado em área inexistente, sobreposta, "
                  "embargada pelo IBAMA/SEMA ou sem matrícula no INCRA/CAR.",
     "gravidade": "Alta",
     "tributos": "ITR, ICMS"},

    # ─── Eixo V — Esquemas Estruturados ─────────────────────────────────────
    {"codigo": "AN-16", "eixo": "V",
     "tipo": "Carrossel fiscal rural",
     "descricao": "Sequência circular de compra e venda entre produtores "
                  "relacionados para multiplicar créditos de "
                  "ICMS/FUNRURAL artificialmente.",
     "gravidade": "Muito Alta",
     "tributos": "ICMS, FUNRURAL"},
    {"codigo": "AN-17", "eixo": "V",
     "tipo": "Emissão em cascata",
     "descricao": "Cadeia de notas encadeadas em que cada elo apenas "
                  "retransmite a mesma mercadoria sem movimentação física real.",
     "gravidade": "Muito Alta",
     "tributos": "ICMS, FUNRURAL"},
    {"codigo": "AN-18", "eixo": "V",
     "tipo": "Caixa dois agropecuário",
     "descricao": "Pagamentos em espécie sem correspondência em extrato "
                  "bancário, GTA ou nota fiscal, com indício de LCDPR "
                  "inconsistente.",
     "gravidade": "Muito Alta",
     "tributos": "IRPF Rural, FUNRURAL, ICMS"},
]


EIXOS_TIPOLOGIAS = {
    "I":   "Manipulação de Valores",
    "II":  "Irregularidade de Partes",
    "III": "Irregularidade de Mercadoria",
    "IV":  "Irregularidade Cadastral e Operacional",
    "V":   "Esquemas Estruturados",
}


# ═══════════════════════════════════════════════════════════════════════════
#  PLANO DE AÇÃO — 3 etapas (30/60/90 dias)
# ═══════════════════════════════════════════════════════════════════════════

def gerar_etapas_recomendacoes(resumo: ResumoFiscal) -> list[Etapa]:
    """Devolve a lista de 3 etapas do plano de ação do modelo.

    As etapas têm itens dinâmicos quando depende de valores apurados (ex:
    "Reconstituir LCDPR 2025 incorporando as 23 notas de compra de R$ X").
    """
    irpf_estim = resumo.irpf_estimado
    funrural_estim = resumo.funrural
    despesa = resumo.F6_despesa
    receita_imed = resumo.F1_receita_imediata

    etapa1 = Etapa(
        numero=1,
        titulo="Aprofundar achados críticos",
        prazo="30 DIAS",
        accent=Severidade.CRITICO,
        itens=[
            "Solicitar ao contribuinte documentação primária dos achados "
            "críticos: GTAs (AGRODEFESA-GO), extratos bancários, "
            "comprovantes de pagamento, ACTs dos leiloeiros e relação "
            "completa de NF-e modelo 55 emitidas pelos leiloeiros em seu nome.",
            "Cruzar com sistemas externos: AGRODEFESA-GO (GTAs e SIDAGRO), "
            "Receita Federal (CAEPF dos PFs recorrentes), SiCAR "
            "(capacidade do imóvel), JUCEG (vínculos societários).",
        ],
    )

    etapa2_itens = [
        f"Reconstituir o LCDPR do período com base no relatório auditado, "
        f"incorporando as notas de compra (R$ {_fmt_brl(despesa)}) e "
        f"separando rigorosamente receita de trânsito.",
        f"Apurar o IRPF Rural (ano-base). Base parcial atual: "
        f"R$ {_fmt_brl(receita_imed - despesa)} (sem arremates). "
        f"IRPF estimado: R$ {_fmt_brl(irpf_estim)}.",
        f"Conferir Funrural recolhido contra a estimativa "
        f"R$ {_fmt_brl(funrural_estim)} deste relatório.",
    ]
    etapa2 = Etapa(
        numero=2,
        titulo="Conformidade fiscal",
        prazo="60 DIAS",
        accent=Severidade.ALTO,
        itens=etapa2_itens,
    )

    etapa3 = Etapa(
        numero=3,
        titulo="Mitigação prospectiva",
        prazo="90 DIAS",
        accent=Severidade.MEDIO,
        itens=[
            "Implantar segregação de fluxos nos sistemas internos: rotina "
            "específica para vendas a PF (com checagem de CAEPF) e outra para "
            "remessas a leilão (com cobrança formal das notas de venda do "
            "leiloeiro).",
            "Adequar à Reforma Tributária (LC 214/2025): a partir de 2027, "
            "CBS substitui PIS/COFINS na cadeia agro. Atualizar emissão de "
            "NFA-e/NF-e com IBS/CBS conforme Nota Técnica 2025.002 RTC.",
        ],
    )

    return [etapa1, etapa2, etapa3]


# ═══════════════════════════════════════════════════════════════════════════
#  REGRA 5 — Cruzamentos com Bases Externas (lista de fontes recomendadas)
# ═══════════════════════════════════════════════════════════════════════════

REGRA_5_CRUZAMENTOS_EXTERNOS: list[dict[str, str]] = [
    {
        "fonte": "AGRODEFESA-GO",
        "o_que_confirmar": "GTA correspondente a cada NFA-e",
        "como_cruzar": "1 GTA para cada nota com gado em trânsito",
    },
    {
        "fonte": "Banco do contribuinte",
        "o_que_confirmar": "Crédito do valor de cada venda",
        "como_cruzar": "Σ depósitos/PIX = Σ receita imediata",
    },
    {
        "fonte": "Leiloeiros (ACTs)",
        "o_que_confirmar": "NF-e modelo 55 do leiloeiro",
        "como_cruzar": "Cada Remessa/Leilão deve gerar venda subsequente",
    },
    {
        "fonte": "Receita Federal (CAEPF)",
        "o_que_confirmar": "Status de produtor rural dos PFs",
        "como_cruzar": "PF sem CAEPF + 3+ compras = revenda informal",
    },
    {
        "fonte": "SEFAZ-GO + SiCAR + JUCEG",
        "o_que_confirmar": "IEs ativas, capacidade do imóvel, vínculos",
        "como_cruzar": "Cabeças/UA ≤ Área CAR; vínculo + venda atípica",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
#  DECLARAÇÃO DE ALCANCE E LIMITAÇÕES
# ═══════════════════════════════════════════════════════════════════════════

DECLARACAO_ALCANCE_LIMITACOES = (
    "Este relatório foi produzido com base no PDF GIEF/SEFAZ-GO e na "
    "Planilha de Gado para IR v5 do sistema OrgAudi 1.1. Os achados "
    "constituem indícios objetivos derivados de cruzamentos lógicos "
    "internos, não confirmados com documentação primária externa (extratos "
    "bancários, GTAs, ACTs, contratos). A confirmação depende de etapa "
    "subsequente de coleta de evidências.\n\n"
    "O presente documento NÃO formula acusações, NÃO imputa dolo e NÃO "
    "substitui procedimento de fiscalização tributária formal. Os elementos "
    "aqui mapeados constituem subsídios técnicos para tomada de decisão do "
    "contribuinte e de seus assessores, e para eventual regularização "
    "espontânea nos termos do art. 138 do CTN."
)


# Catálogo expandido de tipologias forenses — alinhado às 11 do modelo
TIPOLOGIAS_FORENSES: list[str] = [
    "Fragmentação fiscal (smurfing)",
    "Subfaturamento",
    "Uso de 'laranjas'",
    "Lavagem de gado de origem irregular",
    "Conluio com leiloeiro para subdeclaração",
    "Transferência intrafamiliar disfarçada de venda",
    "Emissão a destinatários inexistentes",
    "Intermediação não declarada por PFs",
    "Inconsistência cadastral",
    "Concentração atípica de operações",
    "Sazonalidade incompatível com perfil de produção rotineira",
]
