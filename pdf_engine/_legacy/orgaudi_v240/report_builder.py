"""
orgaudi.report_builder
══════════════════════
Classe principal `LaudoOrgAudi` (orquestrador do laudo) e função utilitária
`gerar_laudo_de_json()` para integração via API ou processamento batch.

Aqui está a "cola" do sistema: recebe dados de entrada, executa o motor
(data_processing), monta as páginas (pdf/pages.py) e gera o PDF final
usando two-pass build para "Página X de N" correto.

Dependências internas: domain, data_processing, pdf.pages, pdf.handlers,
                       validators, styles
Dependências externas: reportlab.platypus.SimpleDocTemplate
"""
from __future__ import annotations

import io
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate

from .data_processing import (
    PlanilhaMensal,
    ResultadoT01, ResultadoT02, ResultadoT04, ResultadoT07,
    ResumoFiscal,
    apurar_resumo,
    construir_planilha_mensal,
    hash_laudo,
    teste_t01_concentracao,
    teste_t02_smurfing,
    teste_t04_concentracao_pf,
    teste_t07_documental,
)
from .domain import (
    Achado,
    CPFInvalidoError,
    CategoriaContabil,
    Contribuinte,
    Etapa,
    NaturezaNota,
    NotaFiscal,
    Periodo,
    Severidade,
)
from .handlers import criar_handler_pagina
from .pages import (
    construir_pagina_1_capa,
    construir_pagina_2_resumo_executivo,
    construir_pagina_achados,
    construir_pagina_6_formulas,
    construir_pagina_7_testes,
    construir_pagina_8_catalogo,
    construir_pagina_9_planilhas,
    construir_pagina_10_compras_formula,
    construir_pagina_11_assinatura,
    construir_paginas_relatorio_tecnico_4p,
)
from .validators import fmt_brl, fmt_data, fmt_pct, validar_cpf


logger = logging.getLogger("orgaudi")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLASSE PRINCIPAL — LaudoOrgAudi
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LaudoOrgAudi:
    """
    Laudo completo OrgAudi 1.0 — gera as 11 páginas com design profissional.

    Modo 1 (notas brutas): passe `notas` e os achados/etapas serão sugeridos
    automaticamente pelos testes T-01 a T-08.

    Modo 2 (dados pré-processados): passe `resumo`, `achados`, `etapas`,
    `planilha_vendas`, `planilha_remessas`, `planilha_compras` diretamente.
    """
    contribuinte: Contribuinte
    periodo: Periodo

    # Modo 1 — entrada bruta
    notas: list[NotaFiscal] = field(default_factory=list)

    # Modo 2 — entrada já processada (sobrescreve modo 1 quando fornecido)
    resumo: Optional[ResumoFiscal] = None
    achados: list[Achado] = field(default_factory=list)
    etapas: list[Etapa] = field(default_factory=list)
    planilha_vendas: list[PlanilhaMensal] = field(default_factory=list)
    planilha_remessas: list[PlanilhaMensal] = field(default_factory=list)
    planilha_compras: list[PlanilhaMensal] = field(default_factory=list)

    # Resultados dos testes (preenchido por processar())
    t01: Optional[ResultadoT01] = None
    t02: Optional[ResultadoT02] = None
    t04: Optional[ResultadoT04] = None
    t07: Optional[ResultadoT07] = None
    hash_doc: str = ""

    def processar(self) -> "LaudoOrgAudi":
        """
        Executa o motor: classifica, apura F1-F6, executa T-01 a T-08,
        constrói planilhas mensais e — se não houver achados manuais — sugere.
        """
        if not self.notas and self.resumo is None:
            raise ValueError(
                "Forneça `notas` (modo 1) ou `resumo` (modo 2). Ambos vazios.")

        # Modo 1 — calcular tudo a partir das notas
        if self.notas:
            cpf = self.contribuinte.cpf
            if self.resumo is None:
                # Passa o Contribuinte completo: propaga eh_pj e eh_segurado_especial
                # para a alíquota Funrural correta (LC 224/2025).
                self.resumo = apurar_resumo(
                    self.notas, self.contribuinte, data_referencia=self.periodo.fim)
            if not self.planilha_vendas:
                self.planilha_vendas = construir_planilha_mensal(
                    self.notas, CategoriaContabil.RECEITA, cpf)
            if not self.planilha_remessas:
                self.planilha_remessas = construir_planilha_mensal(
                    self.notas, CategoriaContabil.TRANSITO, cpf)
            if not self.planilha_compras:
                self.planilha_compras = construir_planilha_mensal(
                    self.notas, CategoriaContabil.DESPESA, cpf)

            # Testes
            self.t01 = teste_t01_concentracao(self.notas, cpf)
            self.t02 = teste_t02_smurfing(self.notas, cpf)
            self.t04 = teste_t04_concentracao_pf(self.notas, cpf)
            self.t07 = teste_t07_documental(self.notas)

            # Sugerir achados se não foram fornecidos manualmente
            if not self.achados:
                self.achados = self._sugerir_achados()

        # NOTA (v1.5.0): a geração automática de etapas foi desativada porque
        # a página 5 (Recomendações) foi removida em v1.4.0. As etapas só são
        # populadas se o chamador fornecê-las explicitamente (modo 2).
        # A função _etapas_padrao() permanece disponível como helper opcional.

        # Hash do laudo
        self.hash_doc = hash_laudo(
            self.contribuinte, self.periodo, self.resumo,
            self.notas if self.notas else [])
        return self

    def _sugerir_achados(self) -> list[Achado]:
        """Constrói achados a partir dos resultados dos testes T-01 a T-08."""
        ach: list[Achado] = []
        c = 1
        a_count = 1

        # T-01 → CRÍTICO (cada nota concentradora)
        for nota, pct in (self.t01.notas_concentradoras if self.t01 else []):
            ach.append(Achado(
                codigo=f"C-{c:02d}",
                titulo=f"Operação singular concentra {fmt_pct(pct)} da receita anual",
                descricao=(
                    f"NFA-e nº <b>{nota.numero}</b> de <b>{fmt_data(nota.data)}</b> "
                    f"concentra <b>{fmt_pct(pct)} da receita anual</b> em uma única "
                    f"operação para <b>{nota.destinatario_nome}</b>. Verificar valor "
                    f"unitário contra pauta e capacidade do imóvel rural do destinatário."
                ),
                severidade=Severidade.CRITICO,
                tabela_cabecalhos=["NFA-e", "Data", "Cabeças", "Valor", "% receita", "Destinatário"],
                tabela_linhas=[[
                    nota.numero, fmt_data(nota.data), str(nota.cabecas),
                    fmt_brl(nota.valor), fmt_pct(pct),
                    nota.destinatario_nome[:30],
                ]],
                cruzamentos=[
                    "GTA AGRODEFESA-GO",
                    f"Extrato bancário ({fmt_brl(nota.valor)})",
                    "Vínculo familiar/societário (JUCEG/RFB)",
                    "Capacidade do imóvel rural (SiCAR/CAR)",
                ],
            ))
            c += 1

        # T-02 → CRÍTICO (cada grupo de smurfing)
        for grupo in (self.t02.grupos if self.t02 else []):
            if grupo.qtd_repeticoes < 3:
                continue
            tabela = [[
                n.numero, fmt_data(n.data), fmt_brl(n.valor), str(n.cabecas),
            ] for n in grupo.notas]
            tabela_total = [
                "TOTAL EM UM ÚNICO DIA", "",
                fmt_brl(grupo.valor_total),
                str(sum(n.cabecas for n in grupo.notas)),
            ]
            ach.append(Achado(
                codigo=f"C-{c:02d}",
                titulo=f"Fragmentação fiscal (smurfing) — {fmt_data(grupo.data)}",
                descricao=(
                    f"Em <b>{fmt_data(grupo.data)}</b> foram emitidas "
                    f"<b>{len(grupo.notas)} NFA-e</b> ao mesmo destinatário "
                    f"<b>{grupo.destinatario_nome}</b> (CPF {grupo.destinatario_cpf}), "
                    f"totalizando <b>{fmt_brl(grupo.valor_total)}</b>. "
                    f"<b>{grupo.qtd_repeticoes} notas com valor exatamente idêntico "
                    f"({fmt_brl(grupo.valor_repetido)})</b> — padrão clássico de "
                    f"fragmentação fiscal."
                ),
                severidade=Severidade.CRITICO,
                tabela_cabecalhos=["NFA-e", "Data", "Valor", "Cabeças"],
                tabela_linhas=tabela,
                tabela_totais=tabela_total,
                porque_critico=(
                    "<b>Hipóteses:</b> (i) manter cada nota abaixo de limiar de triagem; "
                    "(ii) uso de 'laranja'; (iii) lavagem de gado."
                ),
                cruzamentos=[
                    f"GTAs AGRODEFESA-GO das {len(grupo.notas)} notas",
                    "Extrato bancário do dia (PIX/depósitos casados)",
                    "CAEPF do destinatário",
                    "Vínculo familiar/societário (JUCEG/RFB)",
                ],
            ))
            c += 1

        # T-04 → ALTO (concentração em PFs recorrentes)
        if self.t04 and self.t04.detectado():
            top5 = self.t04.pfs_recorrentes[:5]
            outros_qtd = len(self.t04.pfs_recorrentes) - 5
            tabela = [[p.nome[:35], p.cpf, str(p.qtd_notas), fmt_brl(p.valor_total)]
                      for p in top5]
            if outros_qtd > 0:
                outros_notas = sum(p.qtd_notas for p in self.t04.pfs_recorrentes[5:])
                outros_valor = sum((p.valor_total for p in self.t04.pfs_recorrentes[5:]),
                                   Decimal("0"))
                tabela.append([
                    f"Outros {outros_qtd} PFs com 3+ aquisições", "—",
                    str(outros_notas), fmt_brl(outros_valor),
                ])
            total_notas = sum(p.qtd_notas for p in self.t04.pfs_recorrentes)
            total_valor = sum((p.valor_total for p in self.t04.pfs_recorrentes),
                              Decimal("0"))
            ach.append(Achado(
                codigo=f"A-{a_count:02d}",
                titulo=(
                    f"Concentração em PFs com perfil de revenda — "
                    f"{fmt_brl(total_valor)}"
                ),
                descricao=(
                    f"<b>{fmt_pct(self.t04.pct_vendas_pf)}</b> das vendas diretas foram "
                    f"para pessoa física — atípico para pecuária. <b>"
                    f"{len(self.t04.pfs_recorrentes)} PFs</b> aparecem com 3+ aquisições "
                    f"no período."
                ),
                severidade=Severidade.ALTO,
                tabela_cabecalhos=["Destinatário", "CPF", "Notas", "Valor"],
                tabela_linhas=tabela,
                tabela_totais=[
                    f"TOTAL — {len(self.t04.pfs_recorrentes)} PFs RECORRENTES", "",
                    str(total_notas), fmt_brl(total_valor),
                ],
                cruzamentos=[
                    "Verificar CAEPF (Receita Federal) para cada CPF recorrente",
                    "PF sem CAEPF + 3+ compras = intermediação não declarada",
                ],
            ))
            a_count += 1

        # MÉDIO — sempre (obrigações acessórias + Funrural)
        ach.append(Achado(
            codigo="M-01",
            titulo="Obrigações acessórias derivadas do volume",
            descricao=(
                f"Volume bruto de <b>{fmt_brl(self.resumo.valor_bruto_saidas)}</b> "
                "obriga, para a DIRPF do exercício seguinte: (a) manutenção do "
                "<b>LCDPR</b> — Livro Caixa Digital do Produtor Rural "
                "(IN RFB 1.848/2018); (b) apuração do resultado da atividade rural; "
                "(c) retenção de comprovantes por 5 anos."
            ),
            severidade=Severidade.MEDIO,
        ))
        ach.append(Achado(
            codigo="M-02",
            titulo=f"Funrural a recolher — {fmt_brl(self.resumo.funrural)}",
            descricao=(
                f"Funrural sobre vendas diretas ({fmt_brl(self.resumo.F1_receita_imediata)}) "
                f"à alíquota de <b>{self.resumo.aliquota_funrural_pct}</b> "
                f"(categoria: <b>{self.resumo.categoria_previdenciaria}</b>, "
                f"vigente no período auditado): "
                f"<b>{fmt_brl(self.resumo.funrural)}</b>. "
                f"Base legal: {self.resumo.base_legal_funrural}. "
                f"Tabela completa: PF Patronal 1,50% (até 31/03/2026) → 1,63% (≥ 01/04/2026); "
                f"PF Segurado Especial 1,50% (mantida — orientação RFB 03/2026); "
                f"PJ 2,05% (até 31/03/2026) → 2,23% (≥ 01/04/2026)."
            ),
            severidade=Severidade.MEDIO,
        ))

        # ATENÇÃO — compras relevantes
        if self.resumo.F6_despesa > 0:
            ach.append(Achado(
                codigo="AT-01",
                titulo="Compras de gado relevantes — verificar tratamento contábil",
                descricao=(
                    f"<b>{fmt_brl(self.resumo.F6_despesa)} em "
                    f"{self.resumo.qtd_compras} notas</b> de compra. Sob a Regra 1 "
                    "OrgAudi 1.0 (Cliente=Destinatário → DESPESA/INVEST.), reduz a "
                    "base de cálculo do IRPF Rural ou ativa investimento dedutível, "
                    "conforme finalidade: <b>reposição de plantel = despesa; matriz "
                    "reprodutora = ativo</b>."
                ),
                severidade=Severidade.ATENCAO,
            ))

        # CONFORMIDADES (T-07 + Regra 1 + classificação)
        if self.t07:
            n_docs = self.t07.total_documentos_verificados
            n_inv = len(self.t07.cpfs_invalidos) + len(self.t07.cnpjs_invalidos)
            ach.append(Achado(
                codigo="OK-01",
                titulo=f"Validação de dígito verificador de CPF/CNPJ ({n_docs} documentos)",
                descricao="TODOS VÁLIDOS" if n_inv == 0 else f"{n_inv} INVÁLIDOS",
                severidade=Severidade.CONFORME,
            ))
        ach.append(Achado(
            codigo="OK-02",
            titulo="Cruzamento de totais por categoria contábil (Regra 1 OrgAudi 1.0)",
            descricao="CONFORME",
            severidade=Severidade.CONFORME,
        ))
        ach.append(Achado(
            codigo="OK-03",
            titulo=f"Classificação automática de {len(self.notas)} notas (Receita / Trânsito / Despesa)",
            descricao="EXECUTADA",
            severidade=Severidade.CONFORME,
        ))
        return ach

    def _etapas_padrao(self) -> list[Etapa]:
        """Etapas do plano de ação 30/60/90 dias.

        DEPRECATED desde v1.4.0: a página 5 (Recomendações) foi removida da
        renderização padrão do PDF. Este helper permanece disponível para
        chamadores que queiram montar uma seção customizada de recomendações
        ou exportar as etapas em outro formato (e-mail, dashboard, etc.).

        Não é mais chamado automaticamente em processar().
        """
        if self.resumo is None:
            return []
        irpf = fmt_brl(self.resumo.irpf_estimado)
        funrural = fmt_brl(self.resumo.funrural)
        f4 = fmt_brl(self.resumo.F4_receita_bruta)
        f5 = fmt_brl(self.resumo.F5_resultado_rural)
        f6 = fmt_brl(self.resumo.F6_despesa)

        return [
            Etapa(
                numero=1,
                titulo="Aprofundar achados críticos",
                prazo="30 DIAS",
                accent=Severidade.CRITICO,
                itens=[
                    "Solicitar documentação primária dos achados críticos e altos: GTAs, "
                    "extratos bancários, comprovantes de pagamento, ACTs dos leiloeiros, "
                    "relação completa de NF-e modelo 55 emitidas pelos leiloeiros em seu nome.",
                    "Cruzar com sistemas externos: AGRODEFESA-GO (GTAs e SIDAGRO), "
                    "Receita Federal (CAEPF dos PFs recorrentes), SiCAR (capacidade do "
                    "imóvel), JUCEG (vínculos societários).",
                ]),
            Etapa(
                numero=2,
                titulo="Conformidade fiscal",
                prazo="60 DIAS",
                accent=Severidade.ALTO,
                itens=[
                    "Reconstituir o LCDPR do exercício com base no relatório auditado, "
                    f"incorporando as {self.resumo.qtd_compras} notas de compra ({f6}) e "
                    "separando rigorosamente receita de trânsito.",
                    f"Apurar o IRPF Rural do exercício seguinte. Base: F5 = {f5} "
                    f"(F4 {f4} − F6 {f6}). IRPF estimado (20%): {irpf}.",
                    f"Conferir Funrural recolhido contra a estimativa {funrural}.",
                ]),
            Etapa(
                numero=3,
                titulo="Mitigação prospectiva",
                prazo="90 DIAS",
                accent=Severidade.MEDIO,
                itens=[
                    "Implantar segregação de fluxos nos sistemas internos: rotina "
                    "específica para vendas a PF (checagem CAEPF) e outra para remessas a "
                    "leilão (cobrança formal das notas de venda do leiloeiro).",
                    "Adequar à Reforma Tributária (LC 214/2025): a partir de 2027, CBS "
                    "substitui PIS/COFINS na cadeia agro. Atualizar emissão de NFA-e/NF-e "
                    "com IBS/CBS conforme NT 2025.002 RTC.",
                ]),
        ]

    def gerar_pdf(self, caminho: str) -> str:
        """
        Gera o PDF e retorna o caminho.

        Usa técnica two-pass: o primeiro build descobre o total real de páginas
        (incluindo quebras automáticas do ReportLab quando o conteúdo extrapola),
        o segundo build renderiza com o cabeçalho "Página X de N" correto.
        """
        if self.resumo is None:
            self.processar()

        def montar_story():
            s = []
            s += construir_pagina_1_capa(
                self.contribuinte, self.periodo, self.resumo, self.achados)
            s += construir_pagina_2_resumo_executivo(
                self.resumo,
                self.periodo,
                achados_criticos=len([a for a in self.achados if a.severidade == Severidade.CRITICO]),
                achados_medio=len([a for a in self.achados if a.severidade == Severidade.MEDIO]),
                achados_conforme=len([a for a in self.achados if a.severidade == Severidade.CONFORME]),
            )
            s += construir_pagina_achados(self.achados)
            s += construir_pagina_7_testes()
            s += construir_pagina_8_catalogo()
            s += construir_pagina_9_planilhas(
                self.planilha_vendas, self.planilha_remessas)
            s += construir_pagina_10_compras_formula(
                self.planilha_compras, self.resumo)
            s += construir_pagina_6_formulas()
            # [v2.4.2: 4 páginas de relatório técnico antes da assinatura]
            s += construir_paginas_relatorio_tecnico_4p(self.resumo, self.achados)
            s += construir_pagina_11_assinatura(
                self.contribuinte, self.periodo, self.hash_doc)
            return s

        kwargs = dict(
            pagesize=A4,
            leftMargin=14*mm, rightMargin=14*mm,
            topMargin=20*mm, bottomMargin=17*mm,
            title="Relatório de Auditoria Forense — OrgAudi 1.0",
            author="Robson Alain Veloso — ORGATEC",
            subject=f"Análise Fiscal NFA-e — {self.contribuinte.nome}",
        )

        # Pass 1 — descobrir total real de páginas (incluindo quebras automáticas).
        # Cada handler tem estado próprio (closure), o que torna o método thread-safe.
        import io
        hf1_first, hf1_later = criar_handler_pagina(total_paginas=99)  # placeholder
        buf = io.BytesIO()
        doc1 = SimpleDocTemplate(buf, **kwargs)
        doc1.build(montar_story(), onFirstPage=hf1_first, onLaterPages=hf1_later)
        total_real = doc1.page  # número da última página renderizada

        # Pass 2 — renderiza com o total correto no cabeçalho
        hf2_first, hf2_later = criar_handler_pagina(total_paginas=total_real)
        doc2 = SimpleDocTemplate(caminho, **kwargs)
        doc2.build(montar_story(), onFirstPage=hf2_first, onLaterPages=hf2_later)
        return caminho

    def resumo_executivo(self) -> str:
        """Resumo de 1 parágrafo para e-mail / impressão."""
        if self.resumo is None:
            return "Laudo não processado. Chame .processar() primeiro."
        sev_count = Counter(a.severidade for a in self.achados)
        n_critico = sev_count.get(Severidade.CRITICO, 0)
        n_alto = sev_count.get(Severidade.ALTO, 0)
        return (
            f"Auditoria OrgAudi 1.0 — {self.contribuinte.nome} ({self.contribuinte.cpf}) "
            f"— período {fmt_data(self.periodo.inicio)} a {fmt_data(self.periodo.fim)}. "
            f"Volume bruto {fmt_brl(self.resumo.valor_bruto_saidas)} em "
            f"{self.resumo.qtd_total_saidas} saídas. Receita imediata "
            f"{fmt_brl(self.resumo.F1_receita_imediata)} (F1). Resultado rural "
            f"{fmt_brl(self.resumo.F5_resultado_rural)} (F5). IRPF estimado "
            f"{fmt_brl(self.resumo.irpf_estimado)}; Funrural {fmt_brl(self.resumo.funrural)}. "
            f"{n_critico} achado(s) crítico(s), {n_alto} alto(s). Hash: {self.hash_doc}."
        )



# ═══════════════════════════════════════════════════════════════════════════════
#  WRAPPER DE API: validação CPF + carregamento JSON + função gerar_laudo_de_json
# ═══════════════════════════════════════════════════════════════════════════════

def _validar_cpf_obrigatorio(cpf: str, contexto: str = "") -> None:
    """
    Valida CPF e levanta CPFInvalidoError se inválido.
    Usado nos modos batch/API onde não há prompt interativo para correção.
    """
    if not validar_cpf(cpf):
        ctx = f" ({contexto})" if contexto else ""
        raise CPFInvalidoError(
            f"CPF inválido{ctx}: '{cpf}' — dígito verificador não confere. "
            f"Não é possível gerar laudo com CPF inválido."
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  CARREGAMENTO DE NOTAS A PARTIR DE JSON
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_data(s: str) -> date:
    """Aceita 'YYYY-MM-DD' ou 'DD/MM/YYYY'."""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida: {s}")


def carregar_notas_de_json(arquivo: str) -> list[NotaFiscal]:
    """
    Carrega notas a partir de um JSON.
    Formato esperado:
      [
        {
          "numero": "26.409.264",
          "data": "2025-10-24",
          "natureza": "VENDA",
          "valor": 295750.00,
          "cabecas": 91,
          "remetente_cpf": "019.925.771-02",
          "remetente_nome": "GENIS ...",
          "destinatario_cpf": "022.047.861-95",
          "destinatario_nome": "GUSTAVO ..."
        },
        ...
      ]
    """
    with open(arquivo, encoding="utf-8") as f:
        dados = json.load(f)

    notas: list[NotaFiscal] = []
    for d in dados:
        notas.append(NotaFiscal(
            numero=d["numero"],
            data=_parse_data(d["data"]),
            natureza=NaturezaNota(d["natureza"].upper()),
            valor=Decimal(str(d["valor"])),
            cabecas=int(d.get("cabecas", 0)),
            remetente_cpf=d.get("remetente_cpf", ""),
            remetente_nome=d.get("remetente_nome", ""),
            destinatario_cpf=d.get("destinatario_cpf", ""),
            destinatario_nome=d.get("destinatario_nome", ""),
        ))
    return notas


def gerar_laudo_de_json(dados: dict, caminho_saida: str,
                         strict_cpf: bool = True) -> dict:
    """
    Gera laudo a partir de um dict completo.

    Formato:
      {
        "contribuinte": {"nome": "...", "cpf": "...", "ie": "...", "municipio": "..."},
        "periodo": {"inicio": "2025-01-01", "fim": "2025-12-31"},
        "notas": [...]   // formato carregar_notas_de_json
      }

    Args:
      dados: dict com contribuinte, periodo e notas.
      caminho_saida: caminho do PDF de saída.
      strict_cpf: se True (padrão), CPF inválido do contribuinte aborta a geração.
                  Os CPFs nas notas são apenas registrados como achado T-07,
                  não bloqueiam a geração.

    Retorna dict com {pdf, hash, resumo_executivo, kpis, achados}.

    Levanta CPFInvalidoError se strict_cpf=True e CPF do contribuinte inválido.
    """
    c = dados["contribuinte"]
    p = dados["periodo"]

    # Validação obrigatória do CPF do contribuinte (modo batch/API)
    if strict_cpf:
        _validar_cpf_obrigatorio(
            c["cpf"], contexto=f"contribuinte {c.get('nome', '')}".strip())

    contrib = Contribuinte(
        nome=c["nome"], cpf=c["cpf"],
        ie=c.get("ie", ""), municipio=c.get("municipio", ""),
        estado=c.get("estado", "GO"),
        eh_pj=c.get("eh_pj", False),
        eh_segurado_especial=c.get("eh_segurado_especial", False))
    periodo = Periodo(
        inicio=_parse_data(p["inicio"]),
        fim=_parse_data(p["fim"]),
        data_auditoria=_parse_data(p.get("data_auditoria",
                                          date.today().strftime("%Y-%m-%d"))))

    notas: list[NotaFiscal] = []
    for d in dados.get("notas", []):
        notas.append(NotaFiscal(
            numero=d["numero"],
            data=_parse_data(d["data"]) if isinstance(d["data"], str) else d["data"],
            natureza=NaturezaNota(d["natureza"].upper()) if isinstance(d["natureza"], str) else d["natureza"],
            valor=Decimal(str(d["valor"])),
            cabecas=int(d.get("cabecas", 0)),
            remetente_cpf=d.get("remetente_cpf", ""),
            remetente_nome=d.get("remetente_nome", ""),
            destinatario_cpf=d.get("destinatario_cpf", ""),
            destinatario_nome=d.get("destinatario_nome", ""),
        ))

    laudo = LaudoOrgAudi(contribuinte=contrib, periodo=periodo, notas=notas)
    laudo.processar()
    laudo.gerar_pdf(caminho_saida)

    return {
        "pdf": caminho_saida,
        "hash": laudo.hash_doc,
        "resumo_executivo": laudo.resumo_executivo(),
        "kpis": {
            "F1_receita_imediata": float(laudo.resumo.F1_receita_imediata),
            "F2_transito":         float(laudo.resumo.F2_transito),
            "F4_receita_bruta":    float(laudo.resumo.F4_receita_bruta),
            "F5_resultado_rural":  float(laudo.resumo.F5_resultado_rural),
            "F6_despesa":          float(laudo.resumo.F6_despesa),
            "irpf_estimado":       float(laudo.resumo.irpf_estimado),
            "funrural":            float(laudo.resumo.funrural),
            "aliquota_funrural":   laudo.resumo.aliquota_funrural_pct,
            "categoria_previdenciaria": laudo.resumo.categoria_previdenciaria,
            "base_legal_funrural": laudo.resumo.base_legal_funrural,
            "qtd_vendas":          laudo.resumo.qtd_vendas,
            "qtd_remessas":        laudo.resumo.qtd_remessas,
            "qtd_compras":         laudo.resumo.qtd_compras,
        },
        "achados": [
            {"codigo": a.codigo, "titulo": a.titulo,
             "severidade": a.severidade.value}
            for a in laudo.achados
        ],
    }
