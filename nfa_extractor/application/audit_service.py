"""Audit Service — orquestra a consolidação fiscal e persiste o resultado.

Pipeline:
1. Validação estrita do payload via Pydantic (AuditoriaMacroSchema).
2. Execução do motor anti-gravidade (XGBoost/Bayesian proxy).
3. Definição do ciclo de vigilância (FSRS simplificado).
4. Persistência atomic no PostgreSQL/Supabase.

O método sempre rolla back em caso de erro para evitar registros parciais
(garante consistência transacional do banco).
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from nfa_extractor.application.sovereign_engine import AntiGravityQuantEngine
from nfa_extractor.domain.schemas import AuditoriaMacroSchema
from nfa_extractor.infrastructure.database_v2 import ContribuinteAuditoriaMacro

logger = logging.getLogger("AuditController")


def perform_fiscal_consolidation(
    db: Session, fiscal_data: dict
) -> AuditoriaMacroSchema:
    """Orquestra a consolidação fiscal: Validação → Cálculos → Persistência.

    Args:
        db: sessão SQLAlchemy ativa (commit/rollback gerenciados aqui).
        fiscal_data: dict com as chaves esperadas por AuditoriaMacroSchema
            (contribuinte_id, ano_exercicio, total_cabecas_compradas/vendidas,
            valores médios, etc.).

    Returns:
        AuditoriaMacroSchema enriquecido com score_xgboost_final e fraud_flag_level.

    Raises:
        ValidationError: payload inválido (Pydantic).
        SQLAlchemyError: falha na persistência (rollback aplicado).
    """
    try:
        # 1. Validação estrita via Pydantic
        macro_dto = AuditoriaMacroSchema(**fiscal_data)

        # 2. Motor de inteligência (XGBoost/Bayesian proxy)
        engine = AntiGravityQuantEngine()
        calculated_dto = engine.execute_xgboost_bayesian_proxy(macro_dto)
        stab_nova, data_auditoria = engine.define_vigilance_cycle(
            calculated_dto.score_xgboost_final
        )

        # 3. Persistência no PostgreSQL/Supabase
        gap_qty = (
            calculated_dto.total_cabecas_vendidas
            - calculated_dto.total_cabecas_compradas
        )
        db_audit_metric = ContribuinteAuditoriaMacro(
            cpf_cnpj=calculated_dto.contribuinte_id,
            ano_exercicio=calculated_dto.ano_exercicio,
            qty_entradas=calculated_dto.total_cabecas_compradas,
            qty_saidas=calculated_dto.total_cabecas_vendidas,
            gap_qty_animais=gap_qty,
            avg_preco_compra=calculated_dto.avg_preco_compra,
            avg_preco_venda=calculated_dto.avg_preco_venda,
            avg_head_ratio_anomality=calculated_dto.avg_head_ratio_anomality,
            score_risco_bayesian=calculated_dto.score_xgboost_final,
            fraud_flag_level=calculated_dto.fraud_flag_level,
            fsrs_estabilidade=stab_nova,
            proxima_auditoria=data_auditoria,
        )

        db.add(db_audit_metric)
        db.commit()
        db.refresh(db_audit_metric)

        logger.info(
            "auditoria_salva contribuinte=%s fraud_flag=%s score=%.4f",
            macro_dto.contribuinte_id,
            macro_dto.fraud_flag_level,
            calculated_dto.score_xgboost_final,
        )
        return calculated_dto

    except Exception as exc:
        # Rollback obrigatório para liberar a sessão do pool sem registros parciais
        db.rollback()
        logger.exception(
            "fatal_domain_exception contribuinte=%s erro=%s",
            fiscal_data.get("contribuinte_id", "?"),
            exc,
        )
        raise


__all__ = ["perform_fiscal_consolidation"]
