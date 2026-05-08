from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class AuditoriaMacroSchema(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    # Aceita CPF/CNPJ formatado OU só dígitos (Cliente.cpf_cnpj é normalizado
    # para dígitos puros pelo schema clientes.py, mas o pipeline pode receber
    # ambos formatos vindos de outras fontes).
    contribuinte_id: str = Field(
        ...,
        pattern=r'^(\d{11}|\d{14}|\d{3}\.\d{3}\.\d{3}-\d{2}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})$',
    )
    ano_exercicio: int = Field(default=datetime.now().year)
    
    # KPIs Físicos
    total_cabecas_compradas: int = Field(default=0, ge=0)
    total_cabecas_vendidas: int = Field(default=0, ge=0)
    gap_qty_animais: int = Field(default=0)
    
    # KPIs Financeiros
    total_despesa_bruta: float = Field(default=0.0, ge=0.0)
    total_receita_bruta: float = Field(default=0.0, ge=0.0)
    avg_preco_compra: float = Field(default=0.0, ge=0.0)
    avg_preco_venda: float = Field(default=0.0, ge=0.0)
    
    # Detecção Qualitativa Quantitativa (@Sigma)
    avg_head_ratio_anomality: float = Field(default=0.0, description="Distorção Preço Compra/Venda (>1.5 aciona Flag)")
    fraud_flag_level: str = Field(default="NONE") # [NONE, SUSPICIOUS, HIGH_ALERT, SYSTEMIC_FRAUD]
    score_xgboost_final: float = Field(default=0.0, ge=0.0, le=1.0)
