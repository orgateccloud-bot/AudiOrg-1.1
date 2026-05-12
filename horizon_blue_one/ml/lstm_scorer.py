"""LSTM Scorer — Detecção de anomalias temporais em séries de notas fiscais.

Dois modos:
  HEURÍSTICO (padrão): estatísticas de janela deslizante sem ML.
    Detecta aceleração, drift e sazonalidade suspeita via numpy.
  TREINADO: ativado via env LSTM_MODEL_PATH=<path>.pt (PyTorch).
    LSTM bidirecional treinado sobre sequências por produtor.
    Entrada: janelas de 12 notas (valor, cfop_hash, dia_semana, intervalo).
    Saída: anomaly_score 0–1.

Integração: precalc.py chama `calcular_lstm(notas)` → dict com chave "lstm".
O resultado fica em payload["__precalc__"]["lstm"] para S2 @Forense consumir.
"""
from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from datetime import datetime

import numpy as np
import structlog

logger = structlog.get_logger()

# ─── Carregamento lazy do modelo PyTorch ─────────────────────────────────────
_lstm_model          = None
_lstm_model_version  = "heuristic"
_lstm_load_lock      = threading.Lock()
_lstm_load_attempted = False

JANELA_SEQUENCIA = 12   # número de notas por janela LSTM
SIGMA_ALERTA     = 2.5  # desvios padrão para flag de aceleração
THRESHOLD_LSTM   = 0.70 # score acima → anomalia confirmada


def _try_load_model() -> None:
    global _lstm_model, _lstm_model_version, _lstm_load_attempted
    with _lstm_load_lock:
        if _lstm_load_attempted:
            return
        _lstm_load_attempted = True
        model_path = os.environ.get("LSTM_MODEL_PATH", "")
        if not model_path or not os.path.exists(model_path):
            return
        try:
            import torch
            from torch import nn

            class _LSTMAnomalias(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.lstm = nn.LSTM(4, 64, num_layers=2, batch_first=True, bidirectional=True, dropout=0.3)
                    self.fc   = nn.Linear(128, 1)

                def forward(self, x):
                    out, _ = self.lstm(x)
                    return torch.sigmoid(self.fc(out[:, -1, :]))

            model = _LSTMAnomalias()
            model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
            model.eval()
            with open(model_path, "rb") as f:
                version = hashlib.sha256(f.read()).hexdigest()[:12]
            _lstm_model        = model
            _lstm_model_version = version
            logger.info("lstm_carregado", path=model_path, version=version)
        except Exception as exc:
            logger.warning("lstm_falha_carregar", error=str(exc))
            _lstm_model        = None
            _lstm_model_version = "heuristic"


_try_load_model()


# ─── Extração de features por nota ───────────────────────────────────────────

def _feature_nota(nota: dict, media_global: float, std_global: float) -> list[float]:
    """4 features normalizadas: valor, cfop_hash, dia_semana, intervalo."""
    valor = float(nota.get("valor_total", 0))
    valor_norm = (valor - media_global) / (std_global + 1e-9)

    cfop_str = str(nota.get("cfop", "0"))
    # MD5 aqui é feature-hashing determinístico (não criptográfico).
    cfop_hash = (int(hashlib.md5(cfop_str.encode(), usedforsecurity=False).hexdigest(), 16) % 100) / 100.0

    data_str = str(nota.get("data", ""))[:10]
    try:
        dt = datetime.fromisoformat(data_str)
        dia_semana = dt.weekday() / 6.0  # 0=segunda, 1=domingo
    except ValueError:
        dia_semana = 0.0

    return [valor_norm, cfop_hash, dia_semana, 0.0]  # intervalo preenchido pelo agrupamento


def _agrupar_por_produtor(notas: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for n in notas:
        chave = str(n.get("remetente_cnpj", n.get("destinatario_cpf", "DESCONHECIDO")))
        grupos[chave].append(n)
    # Ordena cada grupo por data
    for chave in grupos:
        grupos[chave].sort(key=lambda x: str(x.get("data", "")))
    return dict(grupos)


# ─── Modo heurístico ─────────────────────────────────────────────────────────

def _score_heuristico(notas_prod: list[dict], media_g: float, std_g: float) -> float:
    """Detecta aceleração de volume, drift de preço e concentração temporal."""
    if len(notas_prod) < 3:
        return 0.0

    valores = np.array([float(n.get("valor_total", 0)) for n in notas_prod])
    n = len(valores)

    # 1. Aceleração: segunda metade com volume muito maior que primeira
    metade = n // 2
    if metade > 0:
        media_ini = valores[:metade].mean()
        media_fim = valores[metade:].mean()
        aceleracao = (media_fim - media_ini) / (media_ini + 1e-9)
    else:
        aceleracao = 0.0

    # 2. Outliers de valor (janela deslizante de 6 notas)
    outliers = 0
    for i in range(n):
        ini = max(0, i - 5)
        janela = valores[ini:i + 1]
        if len(janela) >= 3:
            z = abs(valores[i] - janela.mean()) / (janela.std() + 1e-9)
            if z > SIGMA_ALERTA:
                outliers += 1
    taxa_outlier = outliers / n

    # 3. Concentração temporal suspeita (muitas notas na mesma semana)
    datas = []
    for n_nota in notas_prod:
        data_str = str(n_nota.get("data", ""))[:10]
        try:
            datas.append(datetime.fromisoformat(data_str).isocalendar()[1])
        except ValueError:
            pass
    if datas:
        from collections import Counter
        cnt = Counter(datas)
        max_sem = max(cnt.values())
        concentracao = max_sem / len(datas)
    else:
        concentracao = 0.0

    # Score composto (pesos calibrados)
    score = (
        min(max(aceleracao, 0), 1.0) * 0.40
        + taxa_outlier * 0.35
        + min(concentracao, 1.0) * 0.25
    )
    return round(float(np.clip(score, 0.0, 1.0)), 4)


# ─── Modo treinado (PyTorch) ──────────────────────────────────────────────────

def _score_treinado(notas_prod: list[dict], media_g: float, std_g: float) -> float:
    """Inferência LSTM; requer modelo carregado."""
    import torch

    features = [_feature_nota(n, media_g, std_g) for n in notas_prod]

    # Preenche intervalo entre notas
    for i in range(1, len(features)):
        data_str_ant = str(notas_prod[i - 1].get("data", ""))[:10]
        data_str_cur = str(notas_prod[i].get("data", ""))[:10]
        try:
            d_ant = datetime.fromisoformat(data_str_ant)
            d_cur = datetime.fromisoformat(data_str_cur)
            intervalo = min((d_cur - d_ant).days / 365.0, 1.0)
        except ValueError:
            intervalo = 0.0
        features[i][3] = intervalo

    # Janela fixa: pega as últimas JANELA_SEQUENCIA notas ou faz padding
    if len(features) < JANELA_SEQUENCIA:
        padding = [[0.0, 0.0, 0.0, 0.0]] * (JANELA_SEQUENCIA - len(features))
        features = padding + features
    else:
        features = features[-JANELA_SEQUENCIA:]

    x = torch.tensor([features], dtype=torch.float32)
    with torch.no_grad():
        score = float(_lstm_model(x).item())
    return round(score, 4)


# ─── API pública ──────────────────────────────────────────────────────────────

def calcular_lstm(notas: list[dict]) -> dict:
    """Retorna análise temporal LSTM para o lote de notas.

    Returns:
        {
          "modo": "heuristic" | "<hash_modelo>",
          "score_medio": float,          # média entre produtores
          "produtores_anomalos": list,   # produtores com score >= THRESHOLD_LSTM
          "detalhes": {cnpj: score, ...}
        }
    """
    if not notas:
        return {"modo": _lstm_model_version, "score_medio": 0.0,
                "produtores_anomalos": [], "detalhes": {}}

    valores_todos = [float(n.get("valor_total", 0)) for n in notas]
    media_g = float(np.mean(valores_todos)) if valores_todos else 1.0
    std_g   = float(np.std(valores_todos))  if valores_todos else 1.0

    grupos = _agrupar_por_produtor(notas)
    detalhes: dict[str, float] = {}

    usar_treinado = _lstm_model is not None

    for produtor, notas_prod in grupos.items():
        try:
            if usar_treinado:
                score = _score_treinado(notas_prod, media_g, std_g)
            else:
                score = _score_heuristico(notas_prod, media_g, std_g)
        except Exception as exc:
            logger.warning("lstm_scorer_erro", produtor=produtor[:8], error=str(exc))
            score = 0.0
        detalhes[produtor] = score

    scores = list(detalhes.values())
    score_medio = round(float(np.mean(scores)), 4) if scores else 0.0
    anomalos = [p for p, s in detalhes.items() if s >= THRESHOLD_LSTM]

    logger.info(
        "lstm_calculado",
        modo=_lstm_model_version,
        produtores=len(grupos),
        anomalos=len(anomalos),
        score_medio=score_medio,
    )

    return {
        "modo":                _lstm_model_version,
        "score_medio":         score_medio,
        "produtores_anomalos": anomalos,
        "detalhes":            detalhes,
    }
