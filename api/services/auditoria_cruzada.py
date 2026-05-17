"""
api.services.auditoria_cruzada
══════════════════════════════
Orquestrador do fluxo "Auditoria Cruzada" — cruzamento entre dois documentos:

  (1) Planilha de Gado para IR v5 — manutenção contábil interna (ORGATEC);
  (2) Relatório GIEF/SEFAZ-GO — fonte fazendária oficial.

Recebe totais agregados de ambas as fontes e (opcionalmente) o detalhamento
mensal para reprodução da Planilha IR v5 em DOCX. Devolve:

  • Síntese Quantitativa Cruzada (tabela página 1 do PDF de auditoria
    cruzada — indicador, valor planilha, valor PDF, status).
  • Resultado do teste forense T-08 (divergências detectadas).
  • Severidades agregadas (CRÍTICO / ALTO / MÉDIO / ATENÇÃO / CONFORME).
  • Hash de auditabilidade (SHA-256 dos totais cruzados).

A implementação reaproveita `teste_t08_cruzamento_planilha` definido em
`pdf_engine/orgaudi_v240/data_processing.py`.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pdf_engine.orgaudi_v240.data_processing import (
    DivergenciaCruzamento,
    ResultadoT08,
    ResumoFiscal,
    teste_t08_cruzamento_planilha,
)
from pdf_engine.orgaudi_v240.domain import Severidade
from pdf_engine.orgaudi_v240.gerador_achados import (
    CATALOGO_18_ANOMALIAS,
    DECLARACAO_ALCANCE_LIMITACOES,
    EIXOS_TIPOLOGIAS,
    REGRA_5_CRUZAMENTOS_EXTERNOS,
    REGRA_ESPECIAL_1,
    TIPOLOGIAS_FORENSES,
    gerar_achado_at01_compras_relevantes,
    gerar_achados_medios,
    gerar_etapas_recomendacoes,
)


# Resultados de cruzamento mantidos em memória (chave: result_id)
cruzamentos_store: dict[str, dict] = {}


def processar_auditoria_cruzada(request: Any) -> dict:
    """Pipeline da auditoria cruzada.

    Args:
      request: instância do pydantic `CruzamentoRequest` (definido na rota).

    Returns:
      Dicionário com: contribuinte, periodo, sintese_quantitativa,
      teste_t08, severidades, audit_hash, timestamp.
    """
    totais_pl = request.totais_planilha.model_dump()
    totais_gief = request.totais_pdf_gief.model_dump()

    # Executa T-08
    t08 = teste_t08_cruzamento_planilha(totais_pl, totais_gief)

    # Monta Síntese Quantitativa (linhas formatadas para a tabela do PDF)
    sintese = _montar_sintese_quantitativa(t08)

    # Gera achados estruturados de criticidade média (M-01, M-02) e AT-01
    achados_medios = _gerar_achados_medios_serializados(request, totais_pl)
    at01 = _gerar_at01_serializado(request, totais_pl)
    pontos_atencao = [at01] if at01 else []

    # Achados críticos vindos do payload (C-01, C-10, C-03, A-01) — opcionais
    achados_criticos = _serializar_achados_criticos(request)

    # Indicadores principais (KPIs F1-F6 + IRPF + Funrural) para a capa
    indicadores = _calcular_indicadores_principais(request, totais_pl)

    # Conta severidades por categoria (T-08 + achados estruturados + críticos)
    severidades = _agregar_severidades(
        t08, achados_medios + pontos_atencao + achados_criticos)

    # Hash de auditabilidade (determinístico — mesmos totais → mesmo hash)
    audit_hash = _calcular_hash_cruzamento(request, totais_pl, totais_gief)

    return {
        "contribuinte": {
            "cpf": request.contribuinte_cpf,
            "nome": request.contribuinte_nome,
            "ie": getattr(request, "contribuinte_ie", "") or "",
            "municipio": getattr(request, "municipio", "") or "",
            "estado": getattr(request, "estado", "GO") or "GO",
        },
        "periodo": {
            "inicio": request.periodo_inicio,
            "fim": request.periodo_fim,
            "documento_base": getattr(request, "documento_base", "") or "",
        },
        "sintese_quantitativa": sintese,
        "teste_t08": {
            "total_indicadores_comparados": t08.total_indicadores_comparados,
            "qtd_divergencias": len(t08.divergencias),
            "qtd_atencoes": len(t08.atencoes),
            "detectado": t08.detectado(),
            "itens": [_serializar_item_t08(it) for it in t08.itens],
        },
        "severidades": severidades,
        "indicadores_principais": indicadores,
        "achados_criticos": achados_criticos,
        "achados_medios": achados_medios,
        "pontos_atencao": pontos_atencao,
        "etapas_recomendacoes": _gerar_etapas_serializadas(request, totais_pl),
        "regra_5_cruzamentos_externos": REGRA_5_CRUZAMENTOS_EXTERNOS,
        "tipologias_consideradas": TIPOLOGIAS_FORENSES,
        "catalogo_anomalias": CATALOGO_18_ANOMALIAS,
        "eixos_tipologias": EIXOS_TIPOLOGIAS,
        "regra_especial_1": REGRA_ESPECIAL_1,
        "planilha_gado_ir": _serializar_planilha_gado_ir(request, totais_pl),
        "declaracao_alcance": DECLARACAO_ALCANCE_LIMITACOES,
        "audit_hash": audit_hash,
        "sistema": "OrgAudi 1.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _montar_sintese_quantitativa(t08: ResultadoT08) -> list[dict]:
    """Converte itens do T-08 em linhas formatadas para a tabela do PDF."""
    linhas = []
    for item in t08.itens:
        linhas.append({
            "indicador": item.indicador,
            "valor_planilha": _fmt(item.valor_planilha, item.indicador),
            "valor_pdf_gief": _fmt(item.valor_pdf_gief, item.indicador),
            "status": _mapear_status_legivel(item.status),
            "delta": _fmt(item.delta, item.indicador) if item.delta is not None else "—",
            "observacao": item.observacao,
        })
    return linhas


def _mapear_status_legivel(status: str) -> str:
    """Traduz status interno para rótulo da tabela do modelo."""
    return {
        "CONFORME": "Conforme",
        "DIVERGENTE": "Divergente",
        "ATENCAO": "Atenção",
        "DADO_NOVO": "Dado novo",
    }.get(status, status)


def _agregar_severidades(t08: ResultadoT08, achados_medios: list[dict] | None = None) -> dict:
    """Contagem agregada por severidade — replica a tabela do PDF modelo.

    Soma os achados emitidos pelo gerador (M-01, M-02) no nível MÉDIO. Caso
    futuros geradores produzam achados CRITICO/ALTO, basta passá-los na
    mesma lista que a contagem será propagada para o nível correto.
    """
    qtd_divergentes = len(t08.divergencias)
    qtd_atencao = len(t08.atencoes)
    qtd_conforme = sum(1 for i in t08.itens if i.status == "CONFORME")

    contagem = {
        "CRITICO": qtd_divergentes,  # divergência de totais é sempre crítica
        "ALTO": 0,
        "MEDIO": 0,
        "ATENCAO": qtd_atencao,
        "CONFORME": qtd_conforme,
    }

    for a in (achados_medios or []):
        nivel = (a.get("severidade") or "").upper()
        if nivel in contagem:
            contagem[nivel] += 1

    return contagem


def _serializar_item_t08(item: DivergenciaCruzamento) -> dict:
    return {
        "indicador": item.indicador,
        "valor_planilha": str(item.valor_planilha) if item.valor_planilha is not None else None,
        "valor_pdf_gief": str(item.valor_pdf_gief) if item.valor_pdf_gief is not None else None,
        "delta": str(item.delta) if item.delta is not None else None,
        "status": item.status,
        "observacao": item.observacao,
    }


def _calcular_hash_cruzamento(request, totais_pl: dict, totais_gief: dict) -> str:
    """SHA-256 truncado dos inputs — comprova reprodutibilidade do laudo."""
    h = hashlib.sha256()
    h.update(f"{request.contribuinte_cpf}|{request.contribuinte_nome}".encode())
    h.update(f"|{request.periodo_inicio}|{request.periodo_fim}".encode())
    # Ordena chaves para hash determinístico
    for k in sorted(totais_pl):
        h.update(f"|PL.{k}={totais_pl[k]}".encode())
    for k in sorted(totais_gief):
        h.update(f"|GIEF.{k}={totais_gief[k]}".encode())
    return h.hexdigest()[:16].upper()


def _construir_resumo_a_partir_dos_totais(request, totais_pl: dict) -> ResumoFiscal:
    """Adapta os totais agregados em um `ResumoFiscal` mínimo para alimentar
    o gerador de achados M-01/M-02 e o gerador de etapas."""
    resumo = ResumoFiscal(
        eh_pj=getattr(request, "is_pj", False),
        eh_segurado_especial=getattr(request, "is_segurado_especial", False),
    )
    resumo.F1_receita_imediata = Decimal(str(totais_pl.get("receita_imediata") or 0))
    resumo.F2_transito = Decimal(str(totais_pl.get("transito_remessas") or 0))
    resumo.F6_despesa = Decimal(str(totais_pl.get("valor_compras") or 0))
    resumo.F4_receita_bruta = resumo.F1_receita_imediata + resumo.F3_receita_realizada_leilao
    resumo.F5_resultado_rural = resumo.F4_receita_bruta - resumo.F6_despesa
    resumo.qtd_vendas = totais_pl.get("qtd_vendas") or 0
    resumo.qtd_remessas = totais_pl.get("qtd_remessas") or 0
    resumo.qtd_compras = totais_pl.get("qtd_compras") or 0
    resumo.valor_bruto_saidas = (
        resumo.F1_receita_imediata + resumo.F2_transito
    )
    # Data de referência: usa fim do período para escolher alíquota Funrural
    from datetime import datetime as _dt
    try:
        resumo.data_referencia = _dt.strptime(
            request.periodo_fim, "%Y-%m-%d").date()
    except Exception:
        resumo.data_referencia = None
    return resumo


def _gerar_achados_medios_serializados(request, totais_pl: dict) -> list[dict]:
    """M-01 e M-02 em formato JSON-friendly (string severidade, listas)."""
    resumo = _construir_resumo_a_partir_dos_totais(request, totais_pl)
    achados = gerar_achados_medios(resumo)
    return [
        {
            "codigo": a.codigo,
            "titulo": a.titulo,
            "descricao": a.descricao,
            "severidade": a.severidade.value if isinstance(a.severidade, Severidade)
                          else str(a.severidade),
            "porque_critico": a.porque_critico,
            "cruzamentos": list(a.cruzamentos),
        }
        for a in achados
    ]


def _gerar_at01_serializado(request, totais_pl: dict) -> dict | None:
    """AT-01 — Compras de gado relevantes (Ponto de Atenção sobre RE-1)."""
    resumo = _construir_resumo_a_partir_dos_totais(request, totais_pl)
    achado = gerar_achado_at01_compras_relevantes(
        resumo, qtd_compras=totais_pl.get("qtd_compras") or 0)
    if achado is None:
        return None
    return {
        "codigo": achado.codigo,
        "titulo": achado.titulo,
        "descricao": achado.descricao,
        "severidade": achado.severidade.value if isinstance(achado.severidade, Severidade)
                      else str(achado.severidade),
        "porque_critico": achado.porque_critico,
        "cruzamentos": list(achado.cruzamentos),
    }


def _calcular_indicadores_principais(request, totais_pl: dict) -> dict:
    """Bloco de 8 KPIs exibidos na capa (Volume Bruto, F1..F6, IRPF, Funrural)."""
    resumo = _construir_resumo_a_partir_dos_totais(request, totais_pl)

    def _fmt(v) -> str:
        return f"R$ {_format_brl(v)}"

    def _resumido(v) -> str:
        """Formata em K/M para os cards (R$ 3,75M, R$ 730K)."""
        try:
            x = float(v)
        except (TypeError, ValueError):
            return "R$ —"
        if abs(x) >= 1_000_000:
            return f"R$ {x / 1_000_000:.2f}M".replace(".", ",")
        if abs(x) >= 1_000:
            return f"R$ {x / 1_000:.0f}K"
        return f"R$ {x:.2f}".replace(".", ",")

    volume_bruto = resumo.F1_receita_imediata + resumo.F2_transito
    qtd_total_saidas = (totais_pl.get("qtd_vendas") or 0) + (
        totais_pl.get("qtd_remessas") or 0)

    return {
        "VOLUME_BRUTO": {
            "valor": str(volume_bruto), "rotulo": _resumido(volume_bruto),
            "subtitulo": f"{qtd_total_saidas} saídas",
            "valor_completo": _fmt(volume_bruto),
        },
        "F1_RECEITA_IMEDIATA": {
            "valor": str(resumo.F1_receita_imediata),
            "rotulo": _resumido(resumo.F1_receita_imediata),
            "subtitulo": f"{totais_pl.get('qtd_vendas') or 0} vendas · base IRPF",
            "valor_completo": _fmt(resumo.F1_receita_imediata),
        },
        "F2_TRANSITO": {
            "valor": str(resumo.F2_transito),
            "rotulo": _resumido(resumo.F2_transito),
            "subtitulo": f"{totais_pl.get('qtd_remessas') or 0} remessas · não soma",
            "valor_completo": _fmt(resumo.F2_transito),
        },
        "F6_COMPRAS": {
            "valor": str(resumo.F6_despesa),
            "rotulo": _resumido(resumo.F6_despesa),
            "subtitulo": f"{totais_pl.get('qtd_compras') or 0} notas · despesa",
            "valor_completo": _fmt(resumo.F6_despesa),
        },
        "F4_RECEITA_BRUTA": {
            "valor": str(resumo.F4_receita_bruta),
            "rotulo": _resumido(resumo.F4_receita_bruta),
            "subtitulo": "F1 + F3",
            "valor_completo": _fmt(resumo.F4_receita_bruta),
        },
        "F5_RESULTADO_RURAL": {
            "valor": str(resumo.F5_resultado_rural),
            "rotulo": _resumido(resumo.F5_resultado_rural),
            "subtitulo": "F4 − F6 · base IRPF",
            "valor_completo": _fmt(resumo.F5_resultado_rural),
        },
        "IRPF_ESTIMADO": {
            "valor": str(resumo.irpf_estimado),
            "rotulo": _resumido(resumo.irpf_estimado),
            "subtitulo": "20% × F5 · Lei 8.023/90",
            "valor_completo": _fmt(resumo.irpf_estimado),
        },
        "FUNRURAL": {
            "valor": str(resumo.funrural),
            "rotulo": _resumido(resumo.funrural),
            "subtitulo": f"{resumo.aliquota_funrural_pct} × F1 · "
                         f"{resumo.categoria_previdenciaria}",
            "valor_completo": _fmt(resumo.funrural),
        },
    }


def _format_brl(v) -> str:
    """Formata Decimal/float em pt-BR sem prefixo R$."""
    try:
        d = Decimal(str(v))
    except Exception:
        return "—"
    s = f"{d:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _serializar_achados_criticos(request) -> list[dict]:
    """Pega achados críticos opcionais do payload (C-01, C-10, C-03, A-01).

    Os achados são opcionais — o serviço aceita o payload sem eles, e o PDF
    renderiza apenas os blocos presentes. Quando informados, devem seguir o
    formato `{codigo, titulo, descricao, severidade, ...campos opcionais}`.
    """
    raw = getattr(request, "achados_criticos", None) or []
    out = []
    for ach in raw:
        # Aceita tanto pydantic model quanto dict
        if hasattr(ach, "model_dump"):
            ach = ach.model_dump()
        out.append({
            "codigo": ach.get("codigo", "—"),
            "titulo": ach.get("titulo", ""),
            "descricao": ach.get("descricao", ""),
            "severidade": (ach.get("severidade") or "CRITICO").upper(),
            "porque_critico": ach.get("porque_critico", ""),
            "cruzamentos": list(ach.get("cruzamentos") or []),
            "tabela_cabecalhos": list(ach.get("tabela_cabecalhos") or []),
            "tabela_linhas": [list(l) for l in (ach.get("tabela_linhas") or [])],
            "tabela_totais": list(ach.get("tabela_totais") or []),
        })
    return out


def _serializar_planilha_gado_ir(request, totais_pl: dict) -> dict:
    """Tabelas mensais Vendas/Remessas/Compras + Fórmula F1-F6 aplicada."""
    resumo = _construir_resumo_a_partir_dos_totais(request, totais_pl)

    def _dump(lista):
        out = []
        for m in lista or []:
            if hasattr(m, "model_dump"):
                m = m.model_dump()
            out.append({
                "mes": m.get("mes", "—"),
                "qtd_notas": int(m.get("qtd_notas", 0) or 0),
                "cabecas":   int(m.get("cabecas",   0) or 0),
                "valor":     str(m.get("valor",     "0")),
            })
        return out

    vendas = _dump(getattr(request, "vendas_mensais", []))
    remessas = _dump(getattr(request, "remessas_mensais", []))
    compras = _dump(getattr(request, "compras_mensais", []))

    return {
        "vendas":   vendas,
        "remessas": remessas,
        "compras":  compras,
        "totais": {
            "vendas":   _agregar(vendas,   totais_pl, "qtd_vendas",
                                  "receita_imediata"),
            "remessas": _agregar(remessas, totais_pl, "qtd_remessas",
                                  "transito_remessas"),
            "compras":  _agregar(compras,  totais_pl, "qtd_compras",
                                  "valor_compras"),
            "saidas_consolidadas": {
                "qtd_notas": (totais_pl.get("qtd_vendas") or 0)
                             + (totais_pl.get("qtd_remessas") or 0),
                "cabecas":   sum(m["cabecas"] for m in vendas + remessas),
                "valor":     str(resumo.F1_receita_imediata + resumo.F2_transito),
            },
        },
        "formula_regra_2": {
            "F1": {"descricao": "Receita imediata (vendas diretas)",
                   "valor": str(resumo.F1_receita_imediata)},
            "F2": {"descricao": "Trânsito potencial (remessas — NÃO base IRPF)",
                   "valor": str(resumo.F2_transito)},
            "F3": {"descricao": "Receita realizada de leilão (NF-e mod. 55)",
                   "valor": str(resumo.F3_receita_realizada_leilao)},
            "F4": {"descricao": "Receita bruta total DIRPF Rural (F1 + F3)",
                   "valor": str(resumo.F4_receita_bruta)},
            "F6": {"descricao": "Despesa / Investimento dedutível (compras)",
                   "valor": str(resumo.F6_despesa)},
            "F5": {"descricao": "Resultado da atividade rural (F4 − F6)",
                   "valor": str(resumo.F5_resultado_rural)},
        },
    }


def _agregar(linhas: list[dict], totais_pl: dict,
             chave_qtd: str, chave_valor: str) -> dict:
    """Total de uma seção mensal — usa totais autoritativos do payload."""
    return {
        "qtd_notas": totais_pl.get(chave_qtd) or sum(m["qtd_notas"] for m in linhas),
        "cabecas":   sum(m["cabecas"] for m in linhas),
        "valor":     str(totais_pl.get(chave_valor)
                         or sum((Decimal(m["valor"]) for m in linhas), Decimal("0"))),
    }


def _gerar_etapas_serializadas(request, totais_pl: dict) -> list[dict]:
    """Plano de ação 30/60/90 em formato JSON-friendly."""
    resumo = _construir_resumo_a_partir_dos_totais(request, totais_pl)
    etapas = gerar_etapas_recomendacoes(resumo)
    return [
        {
            "numero": e.numero,
            "titulo": e.titulo,
            "prazo": e.prazo,
            "accent": e.accent.value if isinstance(e.accent, Severidade)
                      else str(e.accent),
            "itens": list(e.itens),
        }
        for e in etapas
    ]


def _fmt(valor, indicador: str = "") -> str:
    """Formata valor para exibição na tabela (cabeças → inteiro; resto → BRL)."""
    if valor is None:
        return "—"
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))

    # Indicadores de contagem (cabeças/quantidade) usam inteiro sem R$
    rotulo_lower = indicador.lower()
    if "cabeça" in rotulo_lower or rotulo_lower.startswith("qtd "):
        return f"{int(valor):,}".replace(",", ".")

    formato = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formato}"
