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

# Severidade
SEV = {
    "CRITICO":  {"bg": "#FEF2F2", "border": "#DC2626", "badge": "#DC2626", "dark": "#7F1D1D", "label": "CRÍTICO"},
    "ALTO":     {"bg": "#FFF7ED", "border": "#EA580C", "badge": "#EA580C", "dark": "#7C2D12", "label": "ALTO"},
    "MEDIO":    {"bg": "#EFF6FF", "border": "#2563EB", "badge": "#2563EB", "dark": "#1E3A8A", "label": "MÉDIO"},
    "ATENCAO":  {"bg": "#FFFBEB", "border": "#D97706", "badge": "#D97706", "dark": "#78350F", "label": "ATENÇÃO"},
    "CONFORME": {"bg": "#F0FDF4", "border": "#16A34A", "badge": "#16A34A", "dark": "#14532D", "label": "CONFORME"},
}


def _b64_font(nome: str) -> str:
    """Retorna a fonte como base64 ou '' se não encontrada."""
    p = _FONTS_DIR / nome
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    logger.warning("Fonte não encontrada: %s", p)
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
    return f"""
<div class="page-header">
  <div class="brand">
    <div class="brand-mark"><span>OA</span></div>
    <div>
      <div class="brand-name">ORGATEC</div>
      <div class="brand-sub">CONTABILIDADE E AUDITORIA</div>
    </div>
  </div>
  <div class="page-num">Página {num} de {total}</div>
</div>
<div class="page-header-line"></div>"""


def _page_footer() -> str:
    return """
<div class="page-footer">
  <div class="footer-text">
    ORGATEC CONTABILIDADE E AUDITORIA · Robson Alain Veloso — Ciências Contábeis<br>
    <span style="font-size:5.5pt">Documento de uso restrito — para fins fiscais e contábeis exclusivamente · NBC TA · CPC 47/25/27</span>
  </div>
  <div class="footer-badge">OrgAudi 1.0</div>
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
    """Página 1 — Capa editorial com gradiente."""
    contrib = ctx["contribuinte"]
    periodo = ctx["periodo"]
    resumo  = ctx["resumo"]
    sev_key = ctx.get("sev_key", "CONFORME")
    sev_label = ctx.get("sev_label", "CONFORME")
    n_achados = ctx.get("n_achados", 0)
    n_criticos = ctx.get("n_criticos", 0)
    n_altos = ctx.get("n_altos", 0)
    n_medios = ctx.get("n_medios", 0)
    n_atencao = ctx.get("n_atencao", 0)
    n_conformes = ctx.get("n_conformes", 0)
    hash_doc = ctx.get("hash_doc", "")
    total_pages = ctx.get("total_pages", 6)

    sev_colors = SEV.get(sev_key, SEV["CONFORME"])

    # Bloco de ID do contribuinte
    cpf_fmt = contrib.get("cpf_fmt", "")
    ie = contrib.get("ie", "—")
    municipio = contrib.get("municipio", "")
    estado = contrib.get("estado", "GO")
    periodo_str = contrib.get("periodo_str", "")

    # Mapa de achados
    map_items = [
        (n_criticos, "Crítico",  "#DC2626", "#7F1D1D"),
        (n_altos,    "Alto",     "#EA580C", "#7C2D12"),
        (n_medios,   "Médio",    "#2563EB", "#1E3A8A"),
        (n_atencao,  "Atenção",  "#D97706", "#78350F"),
        (n_conformes,"Conforme", "#16A34A", "#14532D"),
    ]
    map_html = '<div class="achados-map">'
    for cnt, lbl, bg, dark in map_items:
        map_html += f"""
<div class="achados-map-item" style="background:{bg}20;border:1px solid {bg}40">
  <div class="achados-map-count" style="color:{dark}">{cnt}</div>
  <div class="achados-map-label" style="color:{dark}">{lbl}</div>
</div>"""
    map_html += "</div>"

    return f"""
<div class="page" style="background:white;display:flex;flex-direction:column">

  <!-- Capa gradiente (metade superior) -->
  <div style="
    background: linear-gradient(150deg, {NAVY_DK} 0%, {NAVY} 45%, {NAVY_LT} 100%);
    padding: 10mm 14mm 8mm;
    position: relative;
    flex: 0 0 auto;
  ">
    <!-- Topo: logo + paginação -->
    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8mm">
      <div style="display:flex;align-items:center;gap:3mm">
        <div style="
          background:{TEAL};
          border-radius:2mm;
          width:9mm;height:9mm;
          display:flex;align-items:center;justify-content:center;
        ">
          <span style="font-family:'JetBrains Mono',monospace;font-weight:700;font-size:7pt;color:white">OA</span>
        </div>
        <div>
          <div style="font-size:11pt;font-weight:800;color:white;letter-spacing:1px">ORGATEC</div>
          <div style="font-size:7pt;font-weight:400;color:rgba(255,255,255,0.60);letter-spacing:0.5px">CONTABILIDADE E AUDITORIA</div>
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-family:'JetBrains Mono',monospace;font-size:7pt;color:rgba(255,255,255,0.55)">Página 1 de {total_pages}</div>
        <div style="font-size:6.5pt;color:rgba(255,255,255,0.40)">OrgAudi 1.0</div>
      </div>
    </div>

    <!-- Título do laudo -->
    <div style="margin-bottom:2mm">
      <div style="
        font-size:6.5pt;font-weight:600;
        color:{TEAL};
        text-transform:uppercase;letter-spacing:1.5px;
        margin-bottom:2mm;
      ">Relatório de Auditoria Fiscal</div>
      <div style="
        font-size:20pt;font-weight:800;
        color:white;
        line-height:1.15;
        letter-spacing:-0.5px;
      ">{contrib.get('nome', '')}</div>
      <div style="
        font-family:'JetBrains Mono',monospace;
        font-size:9pt;font-weight:400;
        color:rgba(255,255,255,0.70);
        margin-top:1.5mm;
      ">CPF {cpf_fmt}</div>
    </div>

    <!-- Linha teal separadora -->
    <div style="
      height:0.6mm;
      background:linear-gradient(90deg,{TEAL} 0%, transparent 100%);
      margin:4mm 0;
    "></div>

    <!-- Metadados -->
    <div style="display:flex;gap:8mm;flex-wrap:wrap">
      <div>
        <div style="font-size:6pt;font-weight:600;color:rgba(255,255,255,0.50);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5mm">Período auditado</div>
        <div style="font-size:8pt;font-weight:600;color:white">{periodo_str}</div>
      </div>
      <div>
        <div style="font-size:6pt;font-weight:600;color:rgba(255,255,255,0.50);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5mm">Município / UF</div>
        <div style="font-size:8pt;font-weight:600;color:white">{municipio} / {estado}</div>
      </div>
      <div>
        <div style="font-size:6pt;font-weight:600;color:rgba(255,255,255,0.50);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5mm">Insc. Estadual</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:8pt;font-weight:600;color:white">{ie}</div>
      </div>
      <div style="margin-left:auto">
        <div style="font-size:6pt;font-weight:600;color:rgba(255,255,255,0.50);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:0.5mm">Hash</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:6.5pt;color:rgba(255,255,255,0.50)">{hash_doc[:16]}…</div>
      </div>
    </div>
  </div>

  <!-- Conteúdo branco inferior -->
  <div style="padding:6mm 14mm 12mm;flex:1">

    <!-- Risk strip -->
    {_risk_strip(sev_label, sev_key, f"{n_achados} achado(s) · {n_criticos} crítico(s)")}

    <!-- KPIs principais -->
    {_section_header("Síntese Quantitativa", "teal")}
    <div class="kpi-grid">
      <div class="kpi-card {'danger' if float(str(resumo.get('valor_bruto_saidas','0')).replace('R$','').replace('.','').replace(',','.').strip() or '0') > 0 else 'info'}">
        <div class="kpi-label">Receita Bruta</div>
        <div class="kpi-value" style="font-size:9.5pt">{resumo.get('receita_fmt','R$ 0,00')}</div>
        <div class="kpi-sub">{resumo.get('notas_vendas', 0)} NFA-e de venda</div>
      </div>
      <div class="kpi-card warn">
        <div class="kpi-label">Remessas/Trânsito</div>
        <div class="kpi-value" style="font-size:9.5pt">{resumo.get('remessas_fmt','R$ 0,00')}</div>
        <div class="kpi-sub">{resumo.get('notas_remessas', 0)} NFA-e</div>
      </div>
      <div class="kpi-card info">
        <div class="kpi-label">Compras / Despesas</div>
        <div class="kpi-value" style="font-size:9.5pt">{resumo.get('compras_fmt','R$ 0,00')}</div>
        <div class="kpi-sub">{resumo.get('notas_compras', 0)} NFA-e</div>
      </div>
      <div class="kpi-card ok">
        <div class="kpi-label">Funrural Estimado</div>
        <div class="kpi-value" style="font-size:9.5pt">{resumo.get('funrural_fmt','R$ 0,00')}</div>
        <div class="kpi-sub">{resumo.get('aliq_funrural','1,5%')} s/ receita bruta</div>
      </div>
    </div>

    <!-- Mapa de achados -->
    {_section_header("Mapa de Achados por Severidade", "teal")}
    {map_html}

    <!-- Compliance -->
    {_compliance_badges()}

  </div>

  <!-- Rodapé -->
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

    # Página 1 — Capa
    pages_html.append(_pagina_capa(ctx))

    # Página 2 — Resumo executivo
    pages_html.append(_pagina_resumo_executivo(ctx, 2))

    # Páginas de achados — agrupados por severidade
    achados_all = ctx.get("achados", [])
    criticos  = [a for a in achados_all if a.get("severidade_key") == "CRITICO"]
    altos     = [a for a in achados_all if a.get("severidade_key") == "ALTO"]
    medios    = [a for a in achados_all if a.get("severidade_key") in ("MEDIO", "ATENCAO")]
    conformes = [a for a in achados_all if a.get("severidade_key") == "CONFORME"]

    page_num = 3
    if criticos:
        pages_html.append(_pagina_achados(criticos, page_num, ctx["total_pages"],
                                          "Achados Críticos", "CRITICO"))
        page_num += 1
    if altos:
        pages_html.append(_pagina_achados(altos, page_num, ctx["total_pages"],
                                          "Achados de Nível Alto", "ALTO"))
        page_num += 1
    if medios:
        pages_html.append(_pagina_achados(medios, page_num, ctx["total_pages"],
                                          "Achados Médios e Atenção", "MEDIO"))
        page_num += 1
    if conformes:
        pages_html.append(_pagina_achados(conformes, page_num, ctx["total_pages"],
                                          "Conformidades", "CONFORME"))
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
