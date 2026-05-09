"""Limiares (thresholds) de decisão centralizados.

Mantém em UM lugar todas as constantes numéricas que regem decisões dos
agentes S1..S7. Antes estavam espalhadas como magic numbers (ex.:
`score >= 65`, `cfop_div > 5`, `lcdpr > 50_000`), o que dificultava
calibração e auditoria das regras.

Convenção:
  - Valores em USD/BRL: `*_USD` ou `*_BRL`
  - Limiares de score: `SCORE_*` (escala 0..100)
  - Contagens: `*_LIMITE` ou `*_TOLERANCIA`

Calibração só com aprovação do supervisor CRC-GO.
"""
from __future__ import annotations

# ── Score XGBoost (0..100) ────────────────────────────────────────────────────
SCORE_BAIXO    = 40   # < BAIXO  → audit aprovado sem ressalvas
SCORE_ALTO     = 65   # >= ALTO  → ESCALADO para CEO + parecer juridico
SCORE_CRITICO  = 85   # >= CRIT  → upgrade Sonnet→Opus + acao imediata

# ── Tipologias forenses críticas ──────────────────────────────────────────────
TIPOLOGIAS_LIMITE_ESCALA  = 2   # >=2 tipologias → ESCALADO
TIPOLOGIAS_LIMITE_OPUS    = 3   # >=3 tipologias → upgrade Opus

# ── LCDPR (Livro Caixa Digital do Produtor Rural) ─────────────────────────────
LCDPR_TOLERANCIA          = 100.0       # |div| < 100 → CONFORME (arredondamento)
LCDPR_DIVERGENCIA_CRITICA = 50_000.0    # |div| > 50k → CRITICO

# ── CFOP ──────────────────────────────────────────────────────────────────────
CFOP_DIV_LIMITE_FISCAL    = 5    # >5 divergencias no @Fiscal → ESCALADO
CFOP_DIV_LIMITE_NFA       = 10   # >10 no @NFA → CRITICO

# ── ZeroTrust / LGPD ──────────────────────────────────────────────────────────
PENDENCIAS_DOCUMENTAIS_CRITICAS = 10    # >10 pendencias → status CRITICO

# ── Probabilidade de autuação (0..1) ─────────────────────────────────────────
PROB_AUTUACAO_OPUS = 0.75   # >=75% → upgrade Opus

# ── Gate do pipeline (orchestrator, rev 2026-05-09) ──────────────────────────
# Filtra produtores ANTES de chamar S1..S7. Reduz custo ~60% sobre lote real
# preservando rastreabilidade CRC-GO (cada agente que roda tem audit_hash).
PF_GATE_ARQUIVA   = 0.40   # < 0.40 → parecer deterministico, 0 chamadas LLM
PF_GATE_REDUZIDO  = 0.65   # < 0.65 → so S3 + S5 + S7 (fiscal/NFA/CEO)
PF_GATE_AMPLO     = 0.85   # < 0.85 → S1+S2+S3+S5+S7 (sem S4 contabil/S6 RH)
                           # >= 0.85 → pipeline completo S1..S7
