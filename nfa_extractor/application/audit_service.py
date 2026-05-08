from sqlalchemy.orm import Session
import logging

try:
    # Tentativa de import relativo/absoluto dependendo do path de execução
    from nfa_extractor.infrastructure.database_v2 import ContribuinteAuditoriaMacro
    from nfa_extractor.domain.schemas import AuditoriaMacroSchema
    from nfa_extractor.application.sovereign_engine import AntiGravityQuantEngine
except ImportError:
    from nfa_extractor.infrastructure.database_v2 import ContribuinteAuditoriaMacro
    from nfa_extractor.domain.schemas import AuditoriaMacroSchema
    from nfa_extractor.application.sovereign_engine import AntiGravityQuantEngine

logger = logging.getLogger("AuditController")

def perform_fiscal_consolidation(db: Session, fiscal_data: dict) -> AuditoriaMacroSchema:
    """Orquestra a consolidação fiscal: Validação -> Cálculos -> Persistência."""
    try:
        # 1. Validação estrita via Pydantic
        macro_dto = AuditoriaMacroSchema(**fiscal_data)
        
        # 2. Execução do Motor de Inteligência (XGBoost/Bayesian)
        engine = AntiGravityQuantEngine()
        calculated_dto = engine.execute_xgboost_bayesian_proxy(macro_dto)
        stab_nova, data_auditoria = engine.define_vigilance_cycle(calculated_dto.score_xgboost_final)
        
        # 3. Persistência no PostgreSQL
        db_audit_metric = ContribuinteAuditoriaMacro(
            cpf_cnpj=calculated_dto.contribuinte_id,
            ano_exercicio=calculated_dto.ano_exercicio,
            qty_entradas=calculated_dto.total_cabecas_compradas,
            qty_saidas=calculated_dto.total_cabecas_vendidas,
            gap_qty_animais=(calculated_dto.total_cabecas_vendidas - calculated_dto.total_cabecas_compradas),
            avg_preco_compra=calculated_dto.avg_preco_compra,
            avg_preco_venda=calculated_dto.avg_preco_venda,
            avg_head_ratio_anomality=calculated_dto.avg_head_ratio_anomality,
            score_risco_bayesian=calculated_dto.score_xgboost_final,
            fraud_flag_level=calculated_dto.fraud_flag_level,
            fsrs_estabilidade=stab_nova,
            proxima_auditoria=data_auditoria
        )
        
        db.add(db_audit_metric)
        db.commit()
        db.refresh(db_audit_metric)
        
        logger.info(f"AUDITORIA SAVED | CONTRIB: {macro_dto.contribuinte_id} | FRAUD: {macro_dto.fraud_flag_level}")
        return calculated_dto
        
    except Exception as sqle:
        db.rollback() # Previne vazamentos no cache transacional (Antigravity Clean Method)
        logger.critical(f"FATAL DOMAIN EXCEPTION -> Transaction Volatile {str(sqle)}")
        raise
