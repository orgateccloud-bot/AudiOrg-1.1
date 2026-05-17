"""
orgaudi_v250.template_builder
══════════════════════════════
Gera HTML completo e auto-suficiente (fontes base64 embutidas) para o
laudo OrgAudi v2.5.0.

Design specs:
  Formato  : A4 · 210 × 297 mm
  Engine   : Chrome headless (--print-to-pdf)
  Tipografia: Manrope · JetBrains Mono
  Primária : #0B3B5C   Acento: #14B8A6
  Capa     : editorial com gradiente
  Severidade: Crítico · Alto · Médio · Atenção · Conforme
  Conformidade: NBC TA · CPC 47 / 25 / 27
"""
from __future__ import annotations

import base64
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("orgaudi")

# ─── Diretório de fontes ────────────────────────────────────────────────────
_FONTS_DIR = Path(__file__).parent / "assets" / "fonts"

# ─── Paleta de cores ────────────────────────────────────────────────────────
NAVY    = "#0B3B5C"
TEAL    = "#14B8A6"
TEAL_DK = "#0D9488"
TEAL_LT = "#CCFBF1"
SLATE   = "#1E293B"
SLATE_M = "#475569"
SLATE_L = "#94A3B8"
SLATE_BG = "#F1F5F9"
WHITE   = "#FFFFFF"
NAVY_DK = "#072B46"
NAVY_LT = "#1A5276"

# Severidade — cores alinhadas com MODELO ORGATEC v5
SEV = {
    "CRITICO":  {"bg": "#FEF2F2", "border": "#DC2626", "badge": "#DC2626", "dark": "#7F1D1D", "label": "CRÍTICO"},
    "ALTO":     {"bg": "#FFF7ED", "border": "#EA580C", "badge": "#EA580C", "dark": "#7C2D12", "label": "ALTO"},
    "MEDIO":    {"bg": "#EFF6FF", "border": "#2563EB", "badge": "#2563EB", "dark": "#1E3A8A", "label": "MÉDIO"},
    "ATENCAO":  {"bg": "#F5F3FF", "border": "#7C3AED", "badge": "#7C3AED", "dark": "#4C1D95", "label": "ATENÇÃO"},
    "CONFORME": {"bg": "#F0FDF4", "border": "#16A34A", "badge": "#16A34A", "dark": "#14532D", "label": "CONFORME"},
}


def _b64_font(nome: str) -> str:
    """Retorna a fonte como base64 ou '' se não encontrada."""
    p = _FONTS_DIR / nome
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    logger.warning("Fonte não encontrada: %s", p)
    return ""


def _b64_logo() -> str:
    """Retorna o logo ORGATEC como base64 ou '' se não encontrado."""
    p = _FONTS_DIR.parent / "logo_orgatec.png"
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    logger.warning("Logo não encontrado: %s", p)
    return ""


def _css_fonts() -> str:
    """Bloco @font-face com todas as variantes embutidas em base64."""
    pesos = {
        "Manrope": [("300", "manrope-300.ttf"), ("400", "manrope-400.ttf"),
                    ("500", "manrope-500.ttf"), ("600", "manrope-600.ttf"),
                    ("700", "manrope-700.ttf"), ("800", "manrope-800.ttf")],
        "JetBrains Mono": [("400", "jetbrains-400.ttf"), ("500", "jetbrains-500.ttf"),
                           ("700", "jetbrains-700.ttf")],
    }
    css = ""
    for family, variants in pesos.items():
        for weight, fname in variants:
            b64 = _b64_font(fname)
            if b64:
                css += f"""
@font-face {{
  font-family: '{family}';
  font-weight: {weight};
  font-style: normal;
  src: url('data:font/truetype;base64,{b64}') format('truetype');
}}"""
    return css


def _css_base() -> str:
    """CSS base — reset, variáveis, layout A4, tipografia."""
    return f"""
:root {{
  --navy:    {NAVY};
  --navy-dk: {NAVY_DK};
  --navy-lt: {NAVY_LT};
  --teal:    {TEAL};
  --teal-dk: {TEAL_DK};
  --teal-lt: {TEAL_LT};
  --slate:   {SLATE};
  --slate-m: {SLATE_M};
  --slate-l: {SLATE_L};
  --slate-bg:{SLATE_BG};
  --white:   {WHITE};
  --font-main: 'Manrope', 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Consolas', monospace;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body {{
  font-family: var(--font-main);
  font-size: 10pt;
  color: var(--slate);
  background: white;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}

/* ── Página A4 ── */
@page {{
  size: A4;
  margin: 0;
}}

.page {{
  width: 210mm;
  min-height: 297mm;
  max-height: 297mm;
  overflow: hidden;
  position: relative;
  break-before: page;
  page-break-before: always;
}}

.page:first-child {{
  break-before: avoid;
  page-break-before: avoid;
}}

/* ── Cabeçalho padrão (páginas internas) ── */
.page-header {{
  background: var(--navy);
  width: 100%;
  height: 14mm;
  display: flex;
  align-items: center;
  padding: 0 14mm;
  gap: 3mm;
}}

.page-header .brand {{
  display: flex;
  align-items: center;
  gap: 2.5mm;
  flex: 1;
}}

.page-header .brand-mark {{
  width: 7mm;
  height: 7mm;
  border-radius: 1.5mm;
  background: var(--teal);
  display: flex;
  align-items: center;
  justify-content: center;
}}

.page-header .brand-mark span {{
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 5.5pt;
  color: white;
  letter-spacing: -0.5px;
}}

.page-header .brand-name {{
  font-size: 8.5pt;
  font-weight: 700;
  color: white;
  letter-spacing: 0.5px;
}}

.page-header .brand-sub {{
  font-size: 6.5pt;
  font-weight: 400;
  color: rgba(255,255,255,0.60);
  letter-spacing: 0.3px;
  margin-top: 0.5mm;
}}

.page-header .page-num {{
  font-family: var(--font-mono);
  font-size: 7pt;
  font-weight: 500;
  color: rgba(255,255,255,0.70);
  text-align: right;
  white-space: nowrap;
}}

/* Linha teal abaixo do header */
.page-header-line {{
  height: 0.8mm;
  background: linear-gradient(90deg, var(--teal) 0%, var(--teal-dk) 100%);
  width: 100%;
}}

/* ── Conteúdo da página ── */
.page-body {{
  padding: 8mm 14mm 14mm;
  height: calc(297mm - 14mm - 0.8mm - 12mm);
}}

/* ── Rodapé padrão ── */
.page-footer {{
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 12mm;
  border-top: 0.3mm solid {TEAL_LT};
  display: flex;
  align-items: center;
  padding: 0 14mm;
  gap: 6mm;
  background: white;
}}

.page-footer .footer-text {{
  font-size: 6.5pt;
  color: var(--slate-l);
  flex: 1;
  line-height: 1.4;
}}

.page-footer .footer-badge {{
  font-family: var(--font-mono);
  font-size: 6pt;
  font-weight: 500;
  color: var(--teal-dk);
  background: var(--teal-lt);
  padding: 0.8mm 2mm;
  border-radius: 1mm;
  white-space: nowrap;
}}

/* ── Seção header ── */
.section-header {{
  display: flex;
  align-items: center;
  gap: 3mm;
  margin: 5mm 0 3mm;
  padding-bottom: 2mm;
  border-bottom: 0.3mm solid {SLATE_BG};
}}

.section-bar {{
  width: 1mm;
  height: 5mm;
  background: var(--teal);
  border-radius: 0.5mm;
  flex-shrink: 0;
}}

.section-bar.critico  {{ background: #DC2626; }}
.section-bar.alto     {{ background: #EA580C; }}
.section-bar.medio    {{ background: #2563EB; }}
.section-bar.atencao  {{ background: #D97706; }}
.section-bar.conforme {{ background: #16A34A; }}

.section-title {{
  font-size: 9.5pt;
  font-weight: 700;
  color: var(--navy);
  letter-spacing: 0.3px;
  text-transform: uppercase;
}}

.section-count {{
  font-family: var(--font-mono);
  font-size: 7pt;
  font-weight: 500;
  color: var(--slate-m);
  margin-left: auto;
}}

/* ── KPI Grid ── */
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 3mm;
  margin: 3mm 0;
}}

.kpi-card {{
  background: var(--slate-bg);
  border-radius: 2mm;
  padding: 3.5mm 4mm;
  border-left: 1.5mm solid var(--teal);
}}

.kpi-card.danger {{ border-left-color: #DC2626; }}
.kpi-card.warn   {{ border-left-color: #D97706; }}
.kpi-card.ok     {{ border-left-color: #16A34A; }}
.kpi-card.info   {{ border-left-color: #2563EB; }}

.kpi-label {{
  font-size: 6.5pt;
  font-weight: 600;
  color: var(--slate-m);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 1mm;
}}

.kpi-value {{
  font-family: var(--font-mono);
  font-size: 12pt;
  font-weight: 700;
  color: var(--navy);
  line-height: 1;
}}

.kpi-sub {{
  font-size: 6pt;
  color: var(--slate-l);
  margin-top: 1mm;
}}

/* ── Achado card ── */
.achado {{
  border-radius: 2mm;
  margin: 3mm 0;
  overflow: hidden;
  border: 0.3mm solid #E2E8F0;
}}

.achado-header {{
  display: flex;
  align-items: center;
  gap: 3mm;
  padding: 3mm 4mm;
}}

.achado-badge {{
  font-family: var(--font-mono);
  font-size: 7.5pt;
  font-weight: 700;
  color: white;
  padding: 1mm 2.5mm;
  border-radius: 1mm;
  white-space: nowrap;
  flex-shrink: 0;
}}

.achado-title {{
  font-size: 8.5pt;
  font-weight: 700;
  color: white;
  line-height: 1.3;
}}

.achado-body {{
  padding: 4mm;
  background: white;
}}

.achado-desc {{
  font-size: 8pt;
  line-height: 1.5;
  color: var(--slate);
  margin-bottom: 3mm;
}}

.achado-desc b {{ color: var(--navy); }}

/* ── Tabela de achado ── */
.achado-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 7.5pt;
  margin-top: 2mm;
}}

.achado-table th {{
  background: var(--navy);
  color: white;
  padding: 1.5mm 2.5mm;
  text-align: left;
  font-weight: 600;
  font-size: 6.5pt;
  letter-spacing: 0.3px;
}}

.achado-table td {{
  padding: 1.5mm 2.5mm;
  border-bottom: 0.2mm solid #F1F5F9;
  font-family: var(--font-mono);
  font-size: 7pt;
  color: var(--slate);
}}

.achado-table tr:last-child td {{
  border-bottom: none;
}}

.achado-table tr.total td {{
  background: var(--slate-bg);
  font-weight: 700;
  color: var(--navy);
}}

/* ── Cruzamentos ── */
.cruzamentos {{
  margin-top: 3mm;
  padding: 2.5mm 3.5mm;
  background: {TEAL_LT};
  border-radius: 1.5mm;
  border-left: 1.5mm solid var(--teal);
}}

.cruzamentos-title {{
  font-size: 6.5pt;
  font-weight: 700;
  color: var(--teal-dk);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 1.5mm;
}}

.cruzamentos ul {{
  margin: 0;
  padding-left: 4mm;
  font-size: 7pt;
  color: var(--slate-m);
  line-height: 1.6;
}}

/* ── Risk strip (faixa de risco) ── */
.risk-strip {{
  display: flex;
  align-items: stretch;
  border-radius: 2mm;
  overflow: hidden;
  margin: 4mm 0;
}}

.risk-strip-left {{
  flex: 1;
  padding: 4mm 5mm;
  display: flex;
  align-items: center;
  gap: 4mm;
}}

.risk-strip-icon {{
  font-size: 18pt;
  font-weight: 800;
  color: white;
  opacity: 0.9;
  line-height: 1;
  width: 8mm;
  text-align: center;
}}

.risk-strip-text {{}}

.risk-strip-label {{
  font-size: 7pt;
  font-weight: 600;
  color: rgba(255,255,255,0.75);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 0.5mm;
}}

.risk-strip-value {{
  font-size: 13pt;
  font-weight: 800;
  color: white;
  letter-spacing: 0.5px;
  line-height: 1;
}}

.risk-strip-right {{
  background: rgba(0,0,0,0.25);
  padding: 4mm 5mm;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: right;
  min-width: 50mm;
}}

.risk-strip-right .sub {{
  font-size: 6.5pt;
  color: rgba(255,255,255,0.65);
  line-height: 1.5;
}}

/* ── Tabela planilha ── */
.planilha-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 7.5pt;
  margin: 2mm 0;
}}

.planilha-table th {{
  background: var(--navy);
  color: white;
  padding: 2mm 3mm;
  text-align: right;
  font-size: 6.5pt;
  font-weight: 600;
  letter-spacing: 0.3px;
}}

.planilha-table th:first-child {{
  text-align: left;
  width: 28mm;
}}

.planilha-table td {{
  padding: 1.8mm 3mm;
  border-bottom: 0.2mm solid #F1F5F9;
  text-align: right;
  font-family: var(--font-mono);
  font-size: 7pt;
  color: var(--slate);
}}

.planilha-table td:first-child {{
  text-align: left;
  font-family: var(--font-main);
  font-weight: 500;
}}

.planilha-table tr.total td {{
  background: var(--navy);
  color: white;
  font-weight: 700;
  border-bottom: none;
}}

.planilha-table tr.total td:first-child {{
  font-family: var(--font-main);
}}

.planilha-table tr:nth-child(even) td {{
  background: #F8FAFC;
}}

/* ── Conformidade badges ── */
.compliance-row {{
  display: flex;
  gap: 2mm;
  flex-wrap: wrap;
  margin: 2mm 0;
}}

.compliance-badge {{
  font-family: var(--font-mono);
  font-size: 6.5pt;
  font-weight: 600;
  color: var(--teal-dk);
  background: var(--teal-lt);
  padding: 0.8mm 2.5mm;
  border-radius: 1mm;
  border: 0.3mm solid rgba(20,184,166,0.3);
}}

/* ── Declaração final ── */
.declaracao-box {{
  border: 0.5mm solid var(--teal);
  border-radius: 2mm;
  padding: 5mm 6mm;
  margin: 4mm 0;
  background: linear-gradient(135deg, rgba(11,59,92,0.03) 0%, rgba(20,184,166,0.05) 100%);
}}

.assinatura-line {{
  margin-top: 10mm;
  border-top: 0.5mm solid var(--navy);
  width: 70mm;
  padding-top: 2mm;
}}

.assinatura-name {{
  font-size: 8pt;
  font-weight: 700;
  color: var(--navy);
}}

.assinatura-crc {{
  font-size: 7pt;
  color: var(--slate-m);
}}

/* ── Utilitários ── */
.mono {{ font-family: var(--font-mono); }}
.bold {{ font-weight: 700; }}
.navy {{ color: var(--navy); }}
.teal {{ color: var(--teal-dk); }}
.muted {{ color: var(--slate-l); }}
.small {{ font-size: 7pt; }}
.text-right {{ text-align: right; }}

/* ── Mapa de achados (capa) ── */
.achados-map {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 2mm;
  margin: 3mm 0;
}}

.achados-map-item {{
  border-radius: 1.5mm;
  padding: 3mm 2mm;
  text-align: center;
}}

.achados-map-count {{
  font-family: var(--font-mono);
  font-size: 16pt;
  font-weight: 800;
  line-height: 1;
}}

.achados-map-label {{
  font-size: 6pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 1mm;
}}

/* ── Recomendações ── */
.rec-item {{
  display: flex;
  gap: 3mm;
  align-items: flex-start;
  padding: 3mm 0;
  border-bottom: 0.2mm solid {SLATE_BG};
}}

.rec-num {{
  font-family: var(--font-mono);
  font-size: 8pt;
  font-weight: 700;
  color: white;
  background: var(--teal);
  width: 6mm;
  height: 6mm;
  border-radius: 1mm;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}}

.rec-content {{
  flex: 1;
}}

.rec-title {{
  font-size: 8pt;
  font-weight: 700;
  color: var(--navy);
  margin-bottom: 0.8mm;
}}

.rec-desc {{
  font-size: 7.5pt;
  color: var(--slate-m);
  line-height: 1.4;
}}

.rec-prazo {{
  font-family: var(--font-mono);
  font-size: 6.5pt;
  font-weight: 600;
  color: var(--teal-dk);
  white-space: nowrap;
  padding: 0.8mm 2mm;
  background: var(--teal-lt);
  border-radius: 1mm;
  height: fit-content;
}}

/* ── Duas colunas ── */
.two-col {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4mm;
}}

/* ── Tabela id (capa) ── */
.id-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 8pt;
  margin: 2mm 0;
}}

.id-table td {{
  padding: 2mm 0;
  border-bottom: 0.2mm solid {SLATE_BG};
  vertical-align: top;
}}

.id-table td:first-child {{
  color: var(--slate-m);
  font-size: 7pt;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  width: 38mm;
}}

.id-table td:last-child {{
  font-weight: 600;
  color: var(--navy);
  font-family: var(--font-mono);
}}

/* ── Métrica inline ── */
.metric-inline {{
  display: inline-flex;
  align-items: baseline;
  gap: 1.5mm;
}}

.metric-value {{
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 11pt;
  color: var(--navy);
}}

.metric-unit {{
  font-size: 7pt;
  color: var(--slate-m);
}}

/* ── Print overrides ── */
@media print {{
  .page {{ break-inside: avoid; }}
  * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
}}
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS HTML
# ═══════════════════════════════════════════════════════════════════════════════

def _page_header(num: int, total: int) -> str:
    logo_b64 = _b64_logo()
    if logo_b64:
        logo_el = f'<img src="data:image/png;base64,{logo_b64}" style="height:8mm;width:auto;margin-right:2mm">'
    else:
        logo_el = '<div class="brand-mark"><span>OA</span></div>'
    return f"""
<div class="page-header">
  <div class="brand">
    {logo_el}
    <div>
      <div class="brand-name">ORGATEC</div>
      <div class="brand-sub">CONTABILIDADE E AUDITORIA</div>
    </div>
  </div>
  <div class="page-num">Página {num}</div>
</div>
<div class="page-header-line"></div>"""


def _page_footer() -> str:
    return f"""
<div class="page-footer">
  <div class="footer-text" style="text-align:center;font-size:7pt;color:{SLATE_M}">
    ORGATEC CONTABILIDADE E AUDITORIA &nbsp;·&nbsp; Robson Alain Veloso — Ciências Contábeis
  </div>
</div>"""


def _section_header(titulo: str, cor: str = "teal", count: str = "") -> str:
    return f"""
<div class="section-header">
  <div class="section-bar {cor.lower()}"></div>
  <div class="section-title">{titulo}</div>
  {"<div class='section-count'>" + count + "</div>" if count else ""}
</div>"""


def _compliance_badges() -> str:
    badges = ["NBC TA 240", "NBC TA 520", "CPC 47", "CPC 25", "CPC 27", "CTN art. 138", "LC 224/2025"]
    return '<div class="compliance-row">' + "".join(
        f'<span class="compliance-badge">{b}</span>' for b in badges
    ) + "</div>"


def _risk_strip(label: str, sev_key: str, sub: str = "") -> str:
    s = SEV.get(sev_key, SEV["CONFORME"])
    icon = {"CRITICO": "!", "ALTO": "!", "MEDIO": "i", "ATENCAO": "~", "CONFORME": "✓"}.get(sev_key, "i")
    return f"""
<div class="risk-strip" style="background:{s['badge']}">
  <div class="risk-strip-left">
    <div class="risk-strip-icon">{icon}</div>
    <div class="risk-strip-text">
      <div class="risk-strip-label">Nível de Risco Fiscal</div>
      <div class="risk-strip-value">{label}</div>
    </div>
  </div>
  <div class="risk-strip-right">
    <div class="sub">{sub or "OrgAudi 1.0 · ORGATEC"}</div>
  </div>
</div>"""


def _achado_html(achado_data: dict) -> str:
    """Renderiza um achado completo como HTML."""
    sev_key = achado_data.get("severidade_key", "MEDIO")
    s = SEV.get(sev_key, SEV["MEDIO"])
    codigo = achado_data.get("codigo", "X-01")
    titulo = achado_data.get("titulo", "")
    descricao = achado_data.get("descricao", "")
    cabecalhos = achado_data.get("tabela_cabecalhos", [])
    linhas = achado_data.get("tabela_linhas", [])
    totais = achado_data.get("tabela_totais", None)
    cruzamentos = achado_data.get("cruzamentos", [])
    porque = achado_data.get("porque_critico", "")

    table_html = ""
    if cabecalhos:
        ths = "".join(f"<th>{h}</th>" for h in cabecalhos)
        rows = ""
        for linha in linhas:
            cells = "".join(f"<td>{c}</td>" for c in linha)
            rows += f"<tr>{cells}</tr>"
        if totais:
            tcells = "".join(f"<td>{c}</td>" for c in totais)
            rows += f'<tr class="total">{tcells}</tr>'
        table_html = f'<table class="achado-table"><thead><tr>{ths}</tr></thead><tbody>{rows}</tbody></table>'

    cruz_html = ""
    if cruzamentos:
        items = "".join(f"<li>{c}</li>" for c in cruzamentos)
        cruz_html = f"""
<div class="cruzamentos">
  <div class="cruzamentos-title">Cruzamentos Obrigatórios</div>
  <ul>{items}</ul>
</div>"""

    porque_html = ""
    if porque:
        porque_html = f'<p style="font-size:7.5pt;color:{s["dark"]};background:{s["bg"]};padding:2mm 3mm;border-radius:1mm;margin:2mm 0;">{porque}</p>'

    return f"""
<div class="achado">
  <div class="achado-header" style="background:{s['badge']}">
    <div class="achado-badge" style="background:rgba(0,0,0,0.2)">{codigo}</div>
    <div class="achado-title">{titulo}</div>
  </div>
  <div class="achado-body" style="border-left:3px solid {s['border']}">
    <div class="achado-desc">{descricao}</div>
    {porque_html}
    {table_html}
    {cruz_html}
  </div>
</div>"""


def _planilha_table_html(titulo: str, linhas: list[dict], total: dict | None = None) -> str:
    """Tabela mensal de planilha (Vendas, Remessas, Compras)."""
    if not linhas:
        return ""
    ths = "<th>Mês</th><th>Notas</th><th>Cabeças</th><th>Valor R$</th>"
    rows = ""
    for l in linhas:
        rows += f"""<tr>
<td>{l.get('mes','')}</td>
<td>{l.get('qtd_notas', 0)}</td>
<td>{l.get('cabecas', 0)}</td>
<td>{l.get('valor_fmt','')}</td>
</tr>"""
    if total:
        rows += f"""<tr class="total">
<td>TOTAL GERAL</td>
<td>{total.get('qtd_notas','')}</td>
<td>{total.get('cabecas','')}</td>
<td>{total.get('valor_fmt','')}</td>
</tr>"""
    return f"""
{_section_header(titulo, "teal")}
<table class="planilha-table">
  <thead><tr>{ths}</tr></thead>
  <tbody>{rows}</tbody>
</table>"""


# ═══════════════════════════════════════════════════════════════════════════════
#  PÁGINAS
# ═══════════════════════════════════════════════════════════════════════════════

def _pagina_capa(ctx: dict) -> str:
    """Página 1 — Capa estruturada (estilo MODELO ORGATEC v5)."""
    contrib     = ctx["contribuinte"]
    resumo      = ctx["resumo"]
    n_criticos  = ctx.get("n_criticos",  0)
    n_altos     = ctx.get("n_altos",     0)
    n_medios    = ctx.get("n_medios",    0)
    n_atencao   = ctx.get("n_atencao",   0)
    n_conformes = ctx.get("n_conformes", 0)
    total_pages = ctx.get("total_pages", 7)

    # ── Logo para a capa ────────────────────────────────────────────────────
    logo_b64 = _b64_logo()
    if logo_b64:
        logo_capa = f'<img src="data:image/png;base64,{logo_b64}" style="width:15mm;height:auto;display:block;margin:0 auto 1.5mm auto">'
    else:
        logo_capa = (f'<div style="display:inline-flex;align-items:center;justify-content:center;'
                     f'width:12mm;height:12mm;background:{TEAL};border-radius:2mm;margin-bottom:1.5mm">'
                     f'<span style="font-family:\'JetBrains Mono\',monospace;font-weight:800;font-size:8pt;color:white">OA</span></div><br>')

    # ── Tabela de identificação — labels azul-escuro alternado ──────────────
    td_value = f"background:white;color:{SLATE};font-size:8pt;padding:1.6mm 3mm;border:0.25mm solid #d0dde9"
    ident_rows = [
        ("Contribuinte",       contrib.get("nome", "")),
        ("CPF",                contrib.get("cpf_fmt", "")),
        ("Inscrição Estadual", contrib.get("ie", "—")),
        ("Município",          f"{contrib.get('municipio','')} / {contrib.get('estado','GO')}"),
        ("Período auditado",   contrib.get("periodo_str", "")),
        ("Documento-base PDF", "Relatório GIEF/SEFAZ-GO"),
        ("Total de notas",     f"{resumo.get('total_notas', 0)} NFA-e analisadas"),
        ("Volume bruto (saídas)", resumo.get("volume_bruto_fmt", "—")),
        ("Data da auditoria",  resumo.get("data_auditoria", "—")),
    ]
    ident_html = ""
    for i, (k, v) in enumerate(ident_rows):
        bg = NAVY if i % 2 == 0 else NAVY_LT
        td_lbl = f"background:{bg};color:white;font-weight:600;font-size:7.5pt;width:48mm;padding:1.6mm 3mm;border:0.25mm solid {bg}"
        ident_html += f'<tr><td style="{td_lbl}">{k}</td><td style="{td_value}">{v}</td></tr>'

    # ── Síntese quantitativa ─────────────────────────────────────────────────
    th = f"background:{NAVY};color:white;padding:1.5mm 2.5mm;text-align:left;font-size:7pt;font-weight:600"
    td_i  = f"padding:1.5mm 2.5mm;border-bottom:0.2mm solid {SLATE_BG};font-size:7.5pt;color:{SLATE}"
    td_v  = f"padding:1.5mm 2.5mm;border-bottom:0.2mm solid {SLATE_BG};font-size:7.5pt;text-align:right;font-weight:600;color:{NAVY}"
    td_p  = f"padding:1.5mm 2.5mm;border-bottom:0.2mm solid {SLATE_BG};font-size:7.5pt;text-align:center;color:{SLATE_M}"

    vol   = resumo.get("volume_bruto_fmt", "—")
    rec   = resumo.get("receita_fmt", "—")
    rem   = resumo.get("remessas_fmt", "—")
    cab   = resumo.get("cabecas_total", "—")
    dest  = resumo.get("destinatarios_unicos", "—")
    fun   = resumo.get("funrural_fmt", "—")
    rpct  = resumo.get("receita_pct",  "—")
    mpct  = resumo.get("remessas_pct", "—")
    nv    = resumo.get("notas_vendas",   0)
    nr    = resumo.get("notas_remessas", 0)
    aliq  = resumo.get("aliq_funrural", "1,50%")

    sintese_html = f"""
<table style="width:100%;border-collapse:collapse;margin-bottom:3mm">
  <thead>
    <tr>
      <th style="{th}">Indicador</th>
      <th style="{th};width:38mm;text-align:right">Valor</th>
      <th style="{th};width:15mm;text-align:center">%</th>
    </tr>
  </thead>
  <tbody>
    <tr style="background:{SLATE_BG}">
      <td style="{td_i}"><b>Volume bruto movimentado</b></td>
      <td style="{td_v}"><b>{vol}</b></td>
      <td style="{td_p}"><b>100,0%</b></td>
    </tr>
    <tr>
      <td style="{td_i}">Receita imediata (vendas diretas — {nv} notas)</td>
      <td style="{td_v}">{rec}</td>
      <td style="{td_p}">{rpct}</td>
    </tr>
    <tr style="background:{SLATE_BG}">
      <td style="{td_i}">Trânsito (remessa para leilão — {nr} notas)</td>
      <td style="{td_v}">{rem}</td>
      <td style="{td_p}">{mpct}</td>
    </tr>
    <tr>
      <td style="{td_i}">Cabeças totais movimentadas</td>
      <td style="{td_v}">{cab}</td>
      <td style="{td_p}">—</td>
    </tr>
    <tr style="background:{SLATE_BG}">
      <td style="{td_i}">Destinatários únicos (vendas diretas)</td>
      <td style="{td_v}">{dest}</td>
      <td style="{td_p}">—</td>
    </tr>
    <tr>
      <td style="{td_i}">Funrural estimado ({aliq} × vendas diretas)</td>
      <td style="{td_v}">{fun}</td>
      <td style="{td_p}">—</td>
    </tr>
  </tbody>
</table>"""

    # ── Mapa de achados — todos os níveis sempre visíveis ────────────────────
    sev_linhas = [
        ("CRITICO",  "CRÍTICO",  "#DC2626", "#FEF2F2", n_criticos,
         "Fragmentação fiscal, divergência crítica entre fontes"),
        ("ALTO",     "ALTO",     "#EA580C", "#FFF7ED", n_altos,
         "Concentração atípica, sazonalidade anômala"),
        ("MEDIO",    "MÉDIO",    "#2563EB", "#EFF6FF", n_medios,
         "Obrigações acessórias e conferência tributária"),
        ("ATENCAO",  "ATENÇÃO",  "#7C3AED", "#F5F3FF", n_atencao,
         "Indicadores presentes em apenas uma das fontes"),
        ("CONFORME", "CONFORME", "#16A34A", "#F0FDF4", n_conformes,
         "Totais conferidos, CPF/CNPJ válidos, coerência geográfica"),
    ]
    mapa_rows = ""
    for _, lbl, cor, bg, cnt, conclusao in sev_linhas:
        badge = (f'<span style="display:inline-block;background:{cor};color:white;'
                 f'padding:1mm 3mm;border-radius:1mm;'
                 f'font-weight:700;font-size:7.5pt;white-space:nowrap">{lbl}</span>')
        mapa_rows += (
            f'<tr><td style="{td_i};width:30mm">{badge}</td>'
            f'<td style="{td_v};width:12mm;text-align:center">{cnt}</td>'
            f'<td style="{td_i}">{conclusao}</td></tr>'
        )

    mapa_html = f"""
<table style="width:100%;border-collapse:collapse">
  <thead>
    <tr>
      <th style="{th};width:28mm">Severidade</th>
      <th style="{th};width:12mm;text-align:center">Qtd</th>
      <th style="{th}">Conclusão sintética</th>
    </tr>
  </thead>
  <tbody>{mapa_rows}</tbody>
</table>"""

    return f"""
<div class="page">
  {_page_header(1, total_pages)}
  <div class="page-body">

    <!-- Logo + título centralizado -->
    <div style="text-align:center;margin:1mm 0 2mm">
      {logo_capa}
      <div style="font-size:13pt;font-weight:800;color:{NAVY};letter-spacing:0.5px;margin-bottom:0.3mm">ORGATEC</div>
      <div style="font-size:7pt;font-weight:400;color:{SLATE_M};letter-spacing:1.5px;text-transform:uppercase;margin-bottom:2mm">CONTABILIDADE E AUDITORIA</div>
      <div style="font-size:15pt;font-weight:800;color:{NAVY};letter-spacing:-0.3px">RELATÓRIO DE AUDITORIA FORENSE</div>
      <div style="font-size:7.5pt;font-weight:400;color:{SLATE_M};font-style:italic;margin-top:0.5mm">Análise NFA-e GIEF/SEFAZ-GO · Pecuária Bovina</div>
    </div>

    <!-- Tabela de identificação -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:2mm">{ident_html}</table>

    <!-- Síntese Quantitativa -->
    <div style="display:flex;align-items:center;gap:3mm;margin:2mm 0 1.5mm;border-left:3mm solid {NAVY};padding-left:3mm">
      <span style="font-size:8.5pt;font-weight:700;color:{NAVY};text-transform:uppercase;letter-spacing:0.3px">SÍNTESE QUANTITATIVA</span>
    </div>
    {sintese_html}

    <!-- Mapa de Achados -->
    <div style="display:flex;align-items:center;gap:3mm;margin:2mm 0 1.5mm;border-left:3mm solid {NAVY};padding-left:3mm">
      <span style="font-size:8.5pt;font-weight:700;color:{NAVY};text-transform:uppercase;letter-spacing:0.3px">MAPA DE ACHADOS POR SEVERIDADE</span>
    </div>
    {mapa_html}

  </div>
  {_page_footer()}
</div>"""


def _pagina_resumo_executivo(ctx: dict, num: int) -> str:
    """Página 2 — Resumo executivo: KPIs detalhados + planilhas resumidas."""
    resumo = ctx["resumo"]
    contrib = ctx["contribuinte"]
    planilha_vendas = ctx.get("planilha_vendas", [])
    planilha_remessas = ctx.get("planilha_remessas", [])
    total_pages = ctx.get("total_pages", 6)

    return f"""
<div class="page">
  {_page_header(num, total_pages)}
  <div class="page-body">

    {_section_header("Análise Técnica Resumida")}
    <table class="id-table">
      <tr><td>Período auditado</td><td>{resumo.get('periodo_str','')}</td></tr>
      <tr><td>Metodologia</td><td>Análise determinística · 8 testes forenses (T-01 a T-08)</td></tr>
      <tr><td>Base técnica</td><td>Cruzamento lógico interno de NFA-e · sem validação externa</td></tr>
      <tr><td>Escopo</td><td>NFA-e GIEF/SEFAZ-GO · Não inclui NF-e ou NFSe</td></tr>
      <tr><td>Confiabilidade</td><td>Achados críticos requerem coleta de evidências primárias</td></tr>
    </table>

    <div class="two-col" style="margin-top:4mm">
      <div>
        {_section_header("Receitas — Vendas Diretas", "teal")}
        {_planilha_mini(planilha_vendas)}
      </div>
      <div>
        {_section_header("Remessas / Trânsito", "atencao")}
        {_planilha_mini(planilha_remessas)}
      </div>
    </div>

    {_section_header("Ações Recomendadas", "teal")}
    {_recomendacoes(ctx.get('recomendacoes', []))}

  </div>
  {_page_footer()}
</div>"""


def _pagina_recomendacoes(etapas: list[dict], num: int, total_pages: int) -> str:
    """Página de recomendações — 3 etapas (30/60/90 dias), estilo MODELO."""
    etapas_html = ""
    for etapa in etapas:
        titulo = etapa.get("titulo", "")
        prazo  = etapa.get("prazo", "")
        itens  = etapa.get("itens", [])
        itens_html = "".join(
            f'<li style="margin-bottom:1.5mm;font-size:8pt;color:{SLATE};line-height:1.5">{item}</li>'
            for item in itens
        )
        etapas_html += f"""
<div style="margin-bottom:4mm;border:0.3mm solid #E2E8F0;border-radius:2mm;overflow:hidden">
  <div style="background:{NAVY};padding:2.5mm 4mm;display:flex;justify-content:space-between;align-items:center">
    <span style="font-size:8.5pt;font-weight:700;color:white">{titulo}</span>
    <span style="background:{TEAL};color:white;font-family:'JetBrains Mono',monospace;
                 font-size:7pt;font-weight:700;padding:0.8mm 3mm;border-radius:1mm">{prazo}</span>
  </div>
  <div style="padding:3mm 4mm;background:white">
    <ul style="margin:0;padding-left:5mm;line-height:1.6">{itens_html}</ul>
  </div>
</div>"""

    return f"""
<div class="page">
  {_page_header(num, total_pages)}
  <div class="page-body">
    {_section_header("Recomendações e Próximas Etapas", "teal")}
    {etapas_html}
  </div>
  {_page_footer()}
</div>"""


def _pagina_formulas(num: int, total_pages: int) -> str:
    """Página de fórmulas e regras de cruzamento — estática, igual em todos os laudos."""
    th = f"background:{NAVY};color:white;padding:1.5mm 2.5mm;text-align:left;font-size:7pt;font-weight:600"
    td = f"padding:1.5mm 2.5mm;border-bottom:0.2mm solid {SLATE_BG};font-size:7.5pt;color:{SLATE}"

    return f"""
<div class="page">
  {_page_header(num, total_pages)}
  <div class="page-body">
    {_section_header("Fórmulas e Regras de Cruzamento de Dados", "teal")}
    <p style="font-size:7.5pt;color:{SLATE_M};margin-bottom:3mm;line-height:1.4">
      Fórmulas matemáticas e regras de cruzamento aplicadas pelo OrgAudi 1.0 sobre o conjunto de NFA-e.
      Cada regra foi executada nesta auditoria e pode ser reproduzida em qualquer outro caso.
    </p>

    <div style="font-size:8pt;font-weight:700;color:{NAVY};margin:2mm 0 1.5mm">Regra 1 — Classificação contábil das NFA-e</div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:3mm">
      <thead><tr>
        <th style="{th}">Posição do contribuinte</th>
        <th style="{th}">Natureza</th>
        <th style="{th}">Categoria</th>
        <th style="{th}">Efeito IRPF Rural</th>
      </tr></thead>
      <tbody>
        <tr><td style="{td}">REMETENTE</td><td style="{td}">VENDA</td><td style="{td}"><b>RECEITA</b></td><td style="{td}">Soma à base de cálculo</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">REMETENTE</td><td style="{td}">REMESSA/LEILÃO</td><td style="{td}"><b>TRÂNSITO</b></td><td style="{td}">Não soma (até arremate)</td></tr>
        <tr><td style="{td}">REM = DEST (mesmo CPF)</td><td style="{td}">Qualquer</td><td style="{td}"><b>TRANSFERÊNCIA</b></td><td style="{td}">Neutra</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">DESTINATÁRIO</td><td style="{td}">VENDA</td><td style="{td}"><b>DESPESA / INVEST.</b></td><td style="{td}">Subtrai da base ou ativa</td></tr>
      </tbody>
    </table>

    <div style="font-size:8pt;font-weight:700;color:{NAVY};margin:2mm 0 1.5mm">Regra 2 — Fórmulas de apuração da receita rural</div>
    <div style="background:{SLATE_BG};border-radius:2mm;padding:3mm 4mm;margin-bottom:3mm;font-size:7.5pt;line-height:1.8;color:{SLATE}">
      <b>Receita imediata:</b> Σ Valor | Remetente = Contribuinte AND Natureza = VENDA<br>
      <b>Receita em trânsito:</b> Σ Valor | Remetente = Contribuinte AND Natureza = REMESSA/LEILÃO<br>
      <b>Receita de leilão:</b> Σ Valor das NF-e modelo 55 emitidas pelo leiloeiro<br>
      <b>Receita bruta total (DIRPF Rural):</b> Receita imediata + Receita de leilão<br>
      <span style="color:#DC2626"><b>NUNCA usar Receita em trânsito como base — superdimensiona o IRPF.</b></span>
    </div>

    <div style="font-size:8pt;font-weight:700;color:{NAVY};margin:2mm 0 1.5mm">Regra 3 — Fórmulas tributárias</div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:3mm">
      <thead><tr>
        <th style="{th}">Tributo / Contribuição</th>
        <th style="{th}">Fórmula</th>
        <th style="{th}">Base legal</th>
      </tr></thead>
      <tbody>
        <tr><td style="{td}">Funrural PF (até 03/2026)</td><td style="{td}">1,5% × Receita bruta</td><td style="{td}">Lei 8.212/91</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">Funrural PF (a partir 04/2026)</td><td style="{td}">1,63% × Receita bruta</td><td style="{td}">LC 224/2025</td></tr>
        <tr><td style="{td}">Funrural PJ (a partir 04/2026)</td><td style="{td}">2,23% × Receita bruta</td><td style="{td}">LC 224/2025</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">ICMS gado entre produtores</td><td style="{td}">Isento (cria/recria/eng.)</td><td style="{td}">RCTE-GO Anx.IX art.6º XLIII</td></tr>
        <tr><td style="{td}">IRPF Rural (PF)</td><td style="{td}">20% × Resultado rural</td><td style="{td}">Lei 8.023/90 + RIR/2018</td></tr>
      </tbody>
    </table>

    <div style="font-size:8pt;font-weight:700;color:{NAVY};margin:2mm 0 1.5mm">Regra 4 — Cruzamentos forenses de detecção de anomalias</div>
    <table style="width:100%;border-collapse:collapse;margin-bottom:3mm">
      <thead><tr>
        <th style="{th};width:20mm">Teste</th>
        <th style="{th}">Critério matemático</th>
        <th style="{th};width:45mm">Detecta</th>
      </tr></thead>
      <tbody>
        <tr><td style="{td}">T-01 Concentração</td><td style="{td}">1 nota / Receita anual &gt;= 10%</td><td style="{td}">Operações extraordinárias</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">T-02 Smurfing</td><td style="{td}">&gt;=3 notas mesmo dest./dia c/ valores idênticos</td><td style="{td}">Fragmentação fiscal</td></tr>
        <tr><td style="{td}">T-04 Concentração PF</td><td style="{td}">Vendas PF &gt;= 90% E PFs c/ 3+ aquisições</td><td style="{td}">Intermediação não declarada</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">T-05 IE inconsistente</td><td style="{td}">Mesmo CPF/CNPJ vinculado a 2+ IEs</td><td style="{td}">Erro cadastral ou simulação</td></tr>
        <tr><td style="{td}">T-07 Documental</td><td style="{td}">Validação dígito verificador CPF/CNPJ</td><td style="{td}">Documentos forjados</td></tr>
      </tbody>
    </table>

    <div style="font-size:8pt;font-weight:700;color:{NAVY};margin:2mm 0 1.5mm">Regra 5 — Cruzamentos com bases externas</div>
    <table style="width:100%;border-collapse:collapse">
      <thead><tr>
        <th style="{th}">Fonte externa</th>
        <th style="{th}">O que confirmar</th>
        <th style="{th}">Como cruzar</th>
      </tr></thead>
      <tbody>
        <tr><td style="{td}">AGRODEFESA-GO</td><td style="{td}">GTA de cada NFA-e</td><td style="{td}">1 GTA para cada nota com gado em trânsito</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">Banco do contribuinte</td><td style="{td}">Crédito do valor de cada venda</td><td style="{td}">Σ depósitos/PIX = Σ receita imediata</td></tr>
        <tr><td style="{td}">Leiloeiros (ACTs)</td><td style="{td}">NF-e modelo 55 do leiloeiro</td><td style="{td}">Cada remessa deve gerar venda subsequente</td></tr>
        <tr style="background:{SLATE_BG}"><td style="{td}">Receita Federal (CAEPF)</td><td style="{td}">Status produtor rural dos PFs</td><td style="{td}">PF sem CAEPF + 3+ compras = revenda informal</td></tr>
        <tr><td style="{td}">SEFAZ-GO + SiCAR + JUCEG</td><td style="{td}">IEs ativas; imóvel; vínculos</td><td style="{td}">Cabeças/UA &lt;= Área CAR; vínculo + venda atípica</td></tr>
      </tbody>
    </table>

  </div>
  {_page_footer()}
</div>"""


def _planilha_mini(linhas: list[dict]) -> str:
    """Versão compacta da planilha para colunas lado a lado."""
    if not linhas:
        return '<p style="font-size:7.5pt;color:#94A3B8;padding:2mm">Sem movimentação no período.</p>'
    rows = ""
    total_notas = total_cab = 0
    total_val_str = ""
    for l in linhas:
        rows += f"""<tr>
<td>{l.get('mes','')}</td>
<td>{l.get('qtd_notas',0)}</td>
<td>{l.get('valor_fmt','')}</td>
</tr>"""
        total_notas += int(l.get('qtd_notas', 0))
    rows += f'<tr class="total"><td>TOTAL</td><td>{total_notas}</td><td>{linhas[-1].get("valor_acum_fmt","") if linhas else ""}</td></tr>'
    return f"""
<table class="planilha-table" style="font-size:6.5pt">
  <thead><tr><th>Mês</th><th>Notas</th><th>Valor R$</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def _recomendacoes(recs: list[dict]) -> str:
    if not recs:
        return ""
    html = ""
    for i, r in enumerate(recs, 1):
        html += f"""
<div class="rec-item">
  <div class="rec-num">{i:02d}</div>
  <div class="rec-content">
    <div class="rec-title">{r.get('titulo','')}</div>
    <div class="rec-desc">{r.get('descricao','')}</div>
  </div>
  <div class="rec-prazo">{r.get('prazo','')}</div>
</div>"""
    return html


def _pagina_achados(achados_data: list[dict], num: int, total_pages: int,
                    titulo_secao: str, sev_key: str) -> str:
    """Página de achados (pode haver múltiplas)."""
    s = SEV.get(sev_key, SEV["MEDIO"])
    cor_bar = sev_key.lower().replace("medio", "medio")

    achados_html = "".join(_achado_html(a) for a in achados_data)

    return f"""
<div class="page">
  {_page_header(num, total_pages)}
  <div class="page-body">
    {_section_header(titulo_secao, sev_key.lower())}
    {achados_html}
  </div>
  {_page_footer()}
</div>"""


def _pagina_assinatura(ctx: dict, num: int) -> str:
    """Última página — Declaração de alcance + assinatura."""
    hash_doc = ctx.get("hash_doc", "")
    total_pages = ctx.get("total_pages", 6)
    contrib = ctx["contribuinte"]

    return f"""
<div class="page">
  {_page_header(num, total_pages)}
  <div class="page-body">

    {_section_header("Declaração de Alcance e Limitações")}
    <div class="declaracao-box">
      <p style="font-size:8pt;line-height:1.6;color:{SLATE};margin-bottom:3mm">
        Este relatório foi elaborado com base exclusiva no conjunto de Notas Fiscais Avulsas
        Eletrônicas (NFA-e) fornecido pelo sistema GIEF/SEFAZ-GO, extraído pelo sistema
        <strong>NFA Extractor</strong>. A análise é de natureza determinística e documental,
        limitada ao cruzamento lógico interno das informações constantes nas NFA-e informadas.
      </p>
      <p style="font-size:8pt;line-height:1.6;color:{SLATE};margin-bottom:3mm">
        <strong>Não constitui</strong> verificação de campo, auditoria externa, nem conclusão
        definitiva sobre regularidade fiscal. Os achados classificados como Crítico ou Alto
        <strong>requerem coleta de evidências primárias</strong> (extratos bancários, GTAs,
        contratos de leilão) antes de integração em parecer técnico formal.
      </p>
      <p style="font-size:8pt;line-height:1.6;color:{SLATE}">
        <strong>Base legal:</strong> CTN art. 150 (lançamento por homologação) ·
        CTN art. 138 (denúncia espontânea) · IN RFB 1.848/2018 (LCDPR) ·
        Lei 8.023/90 (IRPF Rural) · LC 224/2025 (Funrural) · NBC TA 240 · CPC 47/25/27.
      </p>
    </div>

    <div style="margin-top:5mm">
      {_compliance_badges()}
    </div>

    <div style="display:flex;gap:8mm;align-items:flex-start;margin-top:8mm">
      <div>
        <div class="assinatura-line">
          <div class="assinatura-name">Robson Alain Veloso</div>
          <div class="assinatura-crc">Ciências Contábeis · ORGATEC</div>
        </div>
      </div>
      <div style="margin-left:auto;text-align:right">
        <div style="font-family:'JetBrains Mono',monospace;font-size:6.5pt;color:{SLATE_L}">
          Hash SHA-256 do laudo<br>
          <span style="font-size:7pt;color:{NAVY};font-weight:600">{hash_doc}</span>
        </div>
      </div>
    </div>

  </div>
  {_page_footer()}
</div>"""


# ═══════════════════════════════════════════════════════════════════════════════
#  PONTO DE ENTRADA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

def construir_html(ctx: dict) -> str:
    """
    Gera o HTML completo (self-contained) do laudo.

    ctx deve conter todos os dados necessários para renderização.
    Estrutura esperada: ver report_builder.py → _preparar_ctx().
    """
    # CSS das fontes (base64) + CSS base
    font_css = _css_fonts()
    base_css = _css_base()

    # Coletar páginas
    pages_html = []

    # Página 1 — Capa (estilo MODELO)
    pages_html.append(_pagina_capa(ctx))

    # Páginas de achados — agrupados por severidade
    achados_all = ctx.get("achados", [])
    criticos  = [a for a in achados_all if a.get("severidade_key") == "CRITICO"]
    altos     = [a for a in achados_all if a.get("severidade_key") == "ALTO"]
    medios    = [a for a in achados_all if a.get("severidade_key") in ("MEDIO", "ATENCAO")]
    conformes = [a for a in achados_all if a.get("severidade_key") == "CONFORME"]

    page_num = 2
    if criticos:
        pages_html.append(_pagina_achados(criticos, page_num, ctx["total_pages"],
                                          "Achados Críticos", "CRITICO"))
        page_num += 1
    if altos:
        pages_html.append(_pagina_achados(altos, page_num, ctx["total_pages"],
                                          "Achados de Alta Criticidade", "ALTO"))
        page_num += 1
    if medios:
        pages_html.append(_pagina_achados(medios, page_num, ctx["total_pages"],
                                          "Achados de Criticidade Média", "MEDIO"))
        page_num += 1
    if conformes:
        pages_html.append(_pagina_achados(conformes, page_num, ctx["total_pages"],
                                          "Conformidades Verificadas", "CONFORME"))
        page_num += 1

    # Recomendações e Próximas Etapas
    etapas = ctx.get("etapas", [])
    pages_html.append(_pagina_recomendacoes(etapas, page_num, ctx["total_pages"]))
    page_num += 1

    # Fórmulas e Regras de Cruzamento
    pages_html.append(_pagina_formulas(page_num, ctx["total_pages"]))
    page_num += 1

    # Última página — Assinatura
    pages_html.append(_pagina_assinatura(ctx, ctx["total_pages"]))

    html_body = "\n".join(pages_html)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=210mm">
<title>OrgAudi 1.0 · ORGATEC</title>
<style>
{font_css}
{base_css}
</style>
</head>
<body>
{html_body}
</body>
</html>"""
