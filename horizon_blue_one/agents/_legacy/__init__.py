"""Agentes legados (A-00..A-27) — preservados para regressão / rollback.

Substituídos por S1..S7 a partir de 2026-05-08. Use os novos agentes em
`horizon_blue_one.agents.s1_sentinel..s7_ceo`.

Este módulo NÃO é importado pelo orchestrator novo. Mantido para:
  - Testes de regressão comparando outputs antigos vs novos.
  - Rollback emergencial.
"""
