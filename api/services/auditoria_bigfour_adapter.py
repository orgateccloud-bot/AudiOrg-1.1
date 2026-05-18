"""api.services.auditoria_bigfour_adapter
═══════════════════════════════════════════════════════════════════════════
Adaptador: converte saída do pipeline `auditoria_bigfour` para o schema
canônico `auditoria_v2.json` consumido por `gerar_pdf_auditoria_cruzada`.

Esse módulo isola o bigfour do detalhe de schema do laudo — ele só
precisa passar `notas + veredito_ia + triangulacoes` e recebe um dict
pronto para o gerador canônico.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable


def _fmt_brl(v: Decimal) -> str:
    s = f"{Decimal(str(v)):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _safe_attr(n, name: str, default=None):
    return getattr(n, name, default) if hasattr(n, name) else default


def bigfour_para_schema_auditoria_v2(
    client_name: str,
    client_cpf: str,
    notas: Iterable,
    veredito_ia: str | None = None,
    triangulacoes: list | None = None,
) -> dict:
    """Converte saída do bigfour para o schema auditoria_v2.

    Args:
        client_name : nome do contribuinte.
        client_cpf  : CPF (com ou sem pontuação).
        notas       : iterável de objetos NFA-like (com .valor_total, .natureza,
                       .data_emissao, .destinatario_*, etc.).
        veredito_ia : texto opcional do squad IA — vai como achado AT.
        triangulacoes : lista opcional de cruzamentos — vai como achados C-XX.
    """
    notas = list(notas)
    cpf_limpo = re.sub(r"\D", "", str(client_cpf))
    cpf_fmt = (f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:11]}"
               if len(cpf_limpo) == 11 else cpf_limpo)

    total = sum((Decimal(str(_safe_attr(n, "valor_total", 0) or 0)) for n in notas),
                Decimal(0))
    qtd_v = sum(1 for n in notas
                if str(_safe_attr(n, "natureza", "")).upper().startswith("VENDA"))
    qtd_r = sum(1 for n in notas
                if "REMESSA" in str(_safe_attr(n, "natureza", "")).upper())
    qtd_c = len(notas) - qtd_v - qtd_r

    sintese_gief = [
        {"indicador": "Volume bruto total", "valor_pdf_gief": _fmt_brl(total)},
        {"indicador": "Qtd notas de venda", "valor_pdf_gief": str(qtd_v)},
        {"indicador": "Qtd notas de remessa", "valor_pdf_gief": str(qtd_r)},
        {"indicador": "Qtd notas de compra", "valor_pdf_gief": str(qtd_c)},
    ]

    achados_atencao = []
    if veredito_ia:
        achados_atencao.append({
            "codigo": "AT-IA",
            "titulo": "Veredito do squad de auditoria IA",
            "descricao": veredito_ia[:2000],
            "severidade": "ATENCAO",
            "porque_critico": "Análise multiagente — confirmar com documentação.",
            "cruzamentos": [],
            "tabela_cabecalhos": [],
            "tabela_linhas": [],
            "tabela_totais": [],
        })

    achados_criticos = []
    for i, t in enumerate(triangulacoes or [], 1):
        if isinstance(t, dict):
            achados_criticos.append({
                "codigo": f"TR-{i:02d}",
                "titulo": t.get("titulo", "Triangulação detectada"),
                "descricao": str(t.get("descricao", ""))[:2000],
                "severidade": "CRITICO",
                "porque_critico": t.get("porque_critico", "Padrão suspeito identificado."),
                "cruzamentos": t.get("cruzamentos", []),
                "tabela_cabecalhos": t.get("tabela_cabecalhos", []),
                "tabela_linhas": t.get("tabela_linhas", []),
                "tabela_totais": [],
            })

    sev = {
        "CRITICO": len(achados_criticos),
        "ALTO":    0,
        "MEDIO":   0,
        "ATENCAO": len(achados_atencao),
        "CONFORME": 0,
    }

    return {
        "contribuinte": {
            "cpf": cpf_fmt, "nome": client_name,
            "ie": "", "municipio": "—", "estado": "—",
        },
        "periodo": {
            "inicio": "2025-01-01", "fim": "2025-12-31",
            "documento_base": "Pipeline AuditoriaBigFour OrgAudi 1.1",
        },
        "regra_classificacao": "BigFour multi-agente",
        "sintese_gief": sintese_gief,
        "severidades": sev,
        "indicadores_principais": {
            "VOLUME_BRUTO": {"valor": str(total), "rotulo": _fmt_brl(total),
                              "subtitulo": f"{len(notas)} notas",
                              "valor_completo": _fmt_brl(total)},
        },
        "achados_criticos": achados_criticos,
        "achados_medios":   [],
        "pontos_atencao":   achados_atencao,
        "etapas_recomendacoes": [],
        "declaracao_alcance": (
            "Laudo emitido pelo pipeline BigFour (squad multi-agente IA + "
            "triangulações determinísticas) do OrgAudi 1.1."),
        "audit_hash":   "0" * 64,
        "sistema":      "OrgAudi 1.1 — BigFour",
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "payload_hash": "",
    }
