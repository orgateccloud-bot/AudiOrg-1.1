import numpy as np
from datetime import datetime, timedelta


class AntiGravityQuantEngine:
    """
    Motor de detecção de fraude tributária baseado em proxy Bayesiano.

    Avalia duas dimensões independentes:
    1. Gap físico-contábil: saídas > entradas sem justificativa biológica.
    2. Inversão de preço: preço médio de compra superior ao preço de venda
       (possível mecanismo de dedução fiscal indevida).

    O score final é um float [0.0, MAX_SCORE], onde valores ≥ THRESHOLD_SYSTEMIC
    indicam fraude sistêmica e ≥ THRESHOLD_HIGH_ALERT indicam alto risco.
    """

    # ── Parâmetros do modelo ──────────────────────────────────────────────────
    # Razão compra/venda acima da qual considera-se anomalia de preço (150%)
    DEFAULT_RISK_TRIGGER_RATIO: float = 1.5

    # Peso do gap de quantidade no score (10% do ratio capado)
    GAP_WEIGHT:      float = 0.10
    # Cap do ratio de gap antes da aplicação do peso
    GAP_RATIO_CAP:   float = 5.0

    # Peso da anomalia de preço no score total (80%)
    PRICE_WEIGHT:    float = 0.80
    # Escala da curva sigmoidal para a penalidade de preço
    PRICE_SIGMOID_SCALE: float = 4.0

    # Teto do score (< 1.0 para preservar semântica probabilística)
    MAX_SCORE: float = 0.9982

    # Limiares de severidade
    THRESHOLD_SYSTEMIC:   float = 0.90  # Fraude sistêmica
    THRESHOLD_HIGH_ALERT: float = 0.70  # Alto risco

    # Limiar de perigo para ciclo de vigilância diária
    THRESHOLD_DAILY_WATCH: float = 0.85

    def __init__(self, risk_trigger_ratio: float = DEFAULT_RISK_TRIGGER_RATIO):
        self.risk_trigger_ratio = risk_trigger_ratio

    # ─────────────────────────────────────────────────────────────────────────

    def execute_xgboost_bayesian_proxy(self, dto):
        """
        Calcula o score de risco e atualiza o DTO in-place via object.__setattr__
        (necessário porque AuditoriaMacroSchema usa frozen=True no Pydantic).

        Retorna o próprio DTO enriquecido com:
            - avg_head_ratio_anomality (float, se aplicável)
            - score_xgboost_final      (float)
            - fraud_flag_level         (str)
        """
        risk_factor = 0.0

        # ── 1. Gap físico: saídas > entradas ─────────────────────────────────
        # Penaliza proporcionalmente ao excedente de cabeças vendidas sobre compradas,
        # normalizado pelo volume de compras (+ 1 para evitar divisão por zero).
        fator_abismo = max(0, dto.total_cabecas_vendidas - dto.total_cabecas_compradas)
        gap_ratio    = fator_abismo / (dto.total_cabecas_compradas + 1)
        gap_penalty  = min(gap_ratio, self.GAP_RATIO_CAP) * self.GAP_WEIGHT

        # ── 2. Inversão de preço compra/venda ────────────────────────────────
        # Detecta quando o preço de compra supera o de venda em mais de
        # risk_trigger_ratio — distorção que pode indicar fraude contábil.
        if dto.avg_preco_compra > 0 and dto.avg_preco_venda > 0:
            ratio = dto.avg_preco_compra / dto.avg_preco_venda
            object.__setattr__(dto, 'avg_head_ratio_anomality', ratio)

            if ratio > self.risk_trigger_ratio:
                # Curva sigmoidal: satura suavemente à medida que a distorção cresce.
                sigmoid_input   = -(ratio - self.risk_trigger_ratio) * self.PRICE_SIGMOID_SCALE
                price_mismatch  = 1.0 / (1.0 + np.exp(sigmoid_input))
                risk_factor    += price_mismatch * self.PRICE_WEIGHT

        # ── Score final ───────────────────────────────────────────────────────
        score_final = round(min(risk_factor + gap_penalty, self.MAX_SCORE), 4)
        object.__setattr__(dto, 'score_xgboost_final', score_final)

        # ── Flag de severidade ────────────────────────────────────────────────
        if score_final >= self.THRESHOLD_SYSTEMIC:
            object.__setattr__(dto, 'fraud_flag_level', "SYSTEMIC_FRAUD_TRIBUTARY")
        elif score_final >= self.THRESHOLD_HIGH_ALERT:
            object.__setattr__(dto, 'fraud_flag_level', "HIGH_ALERT")
        else:
            object.__setattr__(dto, 'fraud_flag_level', "NONE")

        return dto

    # ─────────────────────────────────────────────────────────────────────────

    def define_vigilance_cycle(self, risk_score: float, current_stab: float = 1.0) -> tuple[float, datetime]:
        """
        Calcula o próximo ciclo de vigilância usando estabilidade FSRS simplificada.

        Args:
            risk_score:   Score de risco [0.0, MAX_SCORE].
            current_stab: Estabilidade atual (fator de memória FSRS).

        Returns:
            (nova_estabilidade, próxima_data_revisão)
        """
        if risk_score > self.THRESHOLD_DAILY_WATCH:
            # Periculosidade crítica → revisão diária obrigatória
            stab = 0.015
            next_review = datetime.now() + timedelta(days=1)
        else:
            stab        = current_stab * 1.5
            next_review = datetime.now() + timedelta(days=int(stab * 30))
        return stab, next_review
