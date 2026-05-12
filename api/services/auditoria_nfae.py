import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, List

from fastapi import UploadFile
from nfa_extractor.application.agents_engine import rodar_auditoria_completa
from nfa_extractor.domain.extractor import extrair_notas

if TYPE_CHECKING:
    from api.routes.auditoria import AuditoriaCompletaRequest

# Estado de tarefas em memória (substituir por Redis em produção)
tasks_status = {}

# Resultados das auditorias NFA-e (para download)
resultados_store: dict[str, dict] = {}

# Estatísticas acumuladas em memória
_stats = {
    "total_auditorias_nfae": 0,
    "total_notas_processadas": 0,
    "soma_scores": 0.0,
}


def obter_stats_nfae() -> dict:
    count = _stats["total_auditorias_nfae"]
    return {
        "total_auditorias_nfae": count,
        "total_notas_processadas": _stats["total_notas_processadas"],
        "score_medio_nfae": round(_stats["soma_scores"] / count, 1) if count else 0.0,
    }


# ── Pipeline legado: PDF upload → LangGraph (Sigma → Gama → Auditor) ─────────

async def processar_lote_auditoria(
    task_id: str,
    files: List[UploadFile],
    client_name: str,
    client_cpf: str,
):
    try:
        tasks_status[task_id] = {"status": "extraindo", "progress": 10}

        all_notas = []
        temp_dir  = tempfile.gettempdir()

        for file in files:
            file_path = Path(temp_dir) / (file.filename or "")
            # I/O síncrono dentro de async — aceitável para upload pontual.
            with file_path.open("wb") as buffer:
                content = await file.read()
                buffer.write(content)
            notas, _, _ = extrair_notas(str(file_path))
            all_notas.extend(notas)

        tasks_status[task_id] = {"status": "analisando_ia", "progress": 50}
        analise = rodar_auditoria_completa(all_notas, client_name)

        tasks_status[task_id] = {
            "status": "concluido",
            "progress": 100,
            "resultado": analise,
            "total_notas": len(all_notas),
        }

    except Exception as e:
        tasks_status[task_id] = {"status": "erro", "erro": str(e)}


# ── Pipeline HORIZON-BLUE: RE-1 → XGBoost → F1-F6 → A-07 → A-08 ─────────────

async def processar_nfae(request: "AuditoriaCompletaRequest") -> dict:
    """Pipeline completo de auditoria NFA-e integrado com HORIZON-BLUE ONE."""
    from horizon_blue_one.agents.a07_auditoria_assurance import AuditoriaAssuranceAgent
    from horizon_blue_one.agents.a08_auditor_nfa import AuditorNFAAgent
    from horizon_blue_one.agents.base_agent import AgentResult
    from horizon_blue_one.ml.xgboost_scorer import calcular_score
    from horizon_blue_one.orgaudi.regra_especial_1 import aplicar_regra_especial_1
    from horizon_blue_one.orgaudi.resumo_fiscal import apurar_resumo

    notas = [n.model_dump() for n in request.notas]

    # RE-1
    notas_classificadas = [aplicar_regra_especial_1(n) for n in notas]
    notas_re1_aplicada  = sum(
        1 for n in notas_classificadas
        if n.get("regra_aplicada") == "REGRA_ESPECIAL_1"
    )

    # XGBoost
    score_info = calcular_score(notas_classificadas)

    # F1-F6
    resumo = apurar_resumo(
        notas_classificadas,
        eh_pj=request.is_pj,
        eh_segurado_especial=request.is_segurado_especial,
    )

    # A-07 (resiliente)
    try:
        agente_assurance = AuditoriaAssuranceAgent()
        resultado_assurance = await agente_assurance.process({"notas": notas_classificadas})
    except Exception as e:
        resultado_assurance = AgentResult(
            agent_id="A-07", status="ERRO",
            output={"erro": str(e)}, confidence=0.0,
        )

    # A-08 (resiliente)
    try:
        agente_nfa = AuditorNFAAgent()
        resultado_nfa = await agente_nfa.process({
            "notas": notas_classificadas,
            "contribuinte": {
                "cpf":  request.contribuinte_cpf,
                "nome": request.contribuinte_nome,
            },
            "is_pj": request.is_pj,
        })
    except Exception as e:
        resultado_nfa = AgentResult(
            agent_id="A-08", status="ERRO",
            output={"erro": str(e)}, confidence=0.0,
        )

    from pydantic import BaseModel as PydanticBaseModel
    output_nfa = (
        resultado_nfa.output.model_dump()
        if isinstance(resultado_nfa.output, PydanticBaseModel)
        else resultado_nfa.output
    )

    resultado = {
        "status":               resultado_nfa.status,
        "score_risco":          score_info,
        "resumo_fiscal":        resumo.to_dict(),
        "analise_assurance":    resultado_assurance.output,
        "analise_nfa":          output_nfa,
        "notas_classificadas":  notas_classificadas,
        "notas_re1_aplicada":   notas_re1_aplicada,
        "audit_hash":           resultado_nfa.audit_hash,
        "contribuinte": {
            "cpf":    request.contribuinte_cpf,
            "nome":   request.contribuinte_nome,
            "regime": "PJ" if request.is_pj else "Segurado Especial" if request.is_segurado_especial else "PF",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Atualizar estatísticas
    _stats["total_auditorias_nfae"] += 1
    _stats["total_notas_processadas"] += len(notas)
    _stats["soma_scores"] += score_info.get("score", 0)

    return resultado


# ── Geração de PDF simples para download ──────────────────────────────────────

def gerar_pdf_nfae(resultado: dict) -> bytes:
    """Gera PDF compacto do resultado da auditoria NFA-e."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    CYAN   = colors.HexColor("#0ea5e9")
    DARK   = colors.HexColor("#0f172a")
    LIGHT  = colors.HexColor("#f0f9ff")
    story  = []

    titulo = ParagraphStyle("titulo", parent=styles["Title"], textColor=CYAN, fontSize=18)
    h2     = ParagraphStyle("h2", parent=styles["Heading2"], textColor=DARK, fontSize=13)

    story.append(Paragraph("ORGATEC — Relatório de Auditoria NFA-e", titulo))
    story.append(Spacer(1, 6))

    contrib = resultado.get("contribuinte", {})
    story.append(Paragraph(
        f"<b>Contribuinte:</b> {contrib.get('nome', '-')} | "
        f"<b>CPF:</b> {contrib.get('cpf', '-')} | "
        f"<b>Regime:</b> {contrib.get('regime', '-')}",
        styles["Normal"],
    ))
    story.append(Paragraph(
        f"<b>Gerado em:</b> {resultado.get('timestamp', '')[:19].replace('T', ' ')} UTC",
        styles["Normal"],
    ))
    story.append(Spacer(1, 16))

    # Score
    score_info = resultado.get("score_risco", {})
    score_val  = score_info.get("score", 0)
    nivel      = score_info.get("nivel", "-")
    cor_nivel  = {"CRÍTICO": "#ef4444", "ALTO": "#f97316", "MÉDIO": "#eab308", "BAIXO": "#22c55e"}.get(nivel, "#64748b")
    story.append(Paragraph("Score de Risco Fiscal", h2))
    score_tbl = Table(
        [[f"Score: {score_val}", f"Nível: {nivel}", f"Modo: {score_info.get('modo', '-')}"]],
        colWidths=[5*cm, 5*cm, 5*cm],
    )
    score_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(cor_nivel)),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE",   (0, 0), (-1, 0), 12),
        ("ROWPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(score_tbl)
    story.append(Spacer(1, 16))

    # Resumo Fiscal
    story.append(Paragraph("Resumo Fiscal (OrgAudi F1–F6)", h2))
    fiscal = resultado.get("resumo_fiscal", {})
    def fmt(v): return f"R$ {float(v):,.2f}"
    fiscal_rows = [
        ["Campo", "Valor"],
        ["F1 Receita Imediata",      fmt(fiscal.get("f1_receita_imediata", 0))],
        ["F2 Gado em Trânsito",      fmt(fiscal.get("f2_transito", 0))],
        ["F4 Receita Bruta",         fmt(fiscal.get("f4_receita_bruta", 0))],
        ["F6 Despesas Dedutíveis",   fmt(fiscal.get("f6_despesa", 0))],
        ["F5 Resultado Rural",       fmt(fiscal.get("f5_resultado_rural", 0))],
        ["FUNRURAL",                 fmt(fiscal.get("funrural", 0))],
        ["Alíquota FUNRURAL",        f"{float(fiscal.get('aliquota_funrural', 0))*100:.2f}%"],
        ["IRPF Estimado",            fmt(fiscal.get("irpf_estimado", 0))],
        ["Total de Notas",           str(fiscal.get("total_notas", 0))],
    ]
    t = Table(fiscal_rows, colWidths=[9*cm, 7*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), CYAN),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("ROWPADDING",    (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    # RE-1
    re1 = resultado.get("notas_re1_aplicada", 0)
    story.append(Paragraph(f"<b>Regra Especial 1 (VENDA → COMPRA rural):</b> {re1} nota(s) reclassificada(s)", styles["Normal"]))
    story.append(Paragraph(f"<b>Audit Hash:</b> {resultado.get('audit_hash', '-')}", styles["Normal"]))
    story.append(Spacer(1, 16))

    # Análise Assurance
    assurance = resultado.get("analise_assurance", {}) or {}
    if isinstance(assurance, dict) and assurance:
        story.append(Paragraph("Análise Forense (A-07)", h2))
        padroes = assurance.get("padroes_detectados", [])
        rec     = assurance.get("recomendacao", "-")
        crit    = assurance.get("criticidade", "-")
        story.append(Paragraph(f"<b>Recomendação:</b> {rec} | <b>Criticidade:</b> {crit}", styles["Normal"]))
        if padroes:
            story.append(Paragraph(f"<b>Padrões Detectados:</b> {', '.join(padroes)}", styles["Normal"]))
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Documento gerado automaticamente pelo sistema ORGATEC Sovereign Audit v6.4 — HORIZON-BLUE ONE",
        ParagraphStyle("rodape", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#64748b")),
    ))

    doc.build(story)
    return buffer.getvalue()
