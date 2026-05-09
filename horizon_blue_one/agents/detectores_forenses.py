"""Detectores Forenses Determinísticos — sem dependências de LLM ou configuração.

Padrões detectados:
  CARROSSEL_FISCAL   — valores repetidos + CFOP dominante em datas espaçadas
  SMURFING_RURAL     — operações pequenas (<R$10k) concentradas na mesma semana ISO
  FORNECEDOR_FANTASMA — IE ausente/isento em VENDA para DESTINATÁRIO
  DEVOLUCAO_POSTERIOR — venda seguida de devolução parcial (~110%)
  ANOMALIA_TEMPORAL  — valores fora de 2σ do histórico (min. 6 notas)
"""
from collections import Counter
from datetime import datetime

import numpy as np

THRESHOLD_SMURFING = 10_000   # R$ — abaixo disso, suspeito
SIGMA_ANOMALIA     = 2.0      # desvios padrão para anomalia temporal


def detectar_carrossel(notas: list) -> bool:
    valores = [round(float(n.get("valor_total", 0)), 2) for n in notas]
    cnt = Counter(valores)
    repeticoes = sum(1 for v, c in cnt.items() if c >= 3 and v > 0)
    cfops = [n.get("cfop", "") for n in notas]
    cfop_dom = Counter(cfops).most_common(1)
    if cfop_dom and cfop_dom[0][1] / max(len(notas), 1) > 0.85:
        return repeticoes >= 1
    return repeticoes >= 4


def detectar_smurfing(notas: list) -> bool:
    pequenas = [n for n in notas if float(n.get("valor_total", 0)) < THRESHOLD_SMURFING]
    if len(pequenas) < 5:
        return False
    janelas: Counter = Counter()
    for n in pequenas:
        data_str = str(n.get("data", ""))[:10]
        try:
            dt = datetime.fromisoformat(data_str)
            janelas[dt.isocalendar()[1]] += 1
        except ValueError:
            pass
    return any(v >= 5 for v in janelas.values())


def detectar_fornecedor_fantasma(notas: list) -> list[str]:
    suspeitos = []
    for n in notas:
        ie      = str(n.get("ie_remetente", "")).strip()
        natureza = str(n.get("natureza", "")).upper()
        posicao  = str(n.get("posicao", "")).upper()
        if "DESTIN" in posicao and "VENDA" in natureza:
            if not ie or ie.upper() in ("", "ISENTO", "NAO CONTRIBUINTE"):
                suspeitos.append(str(n.get("numero", n.get("id", "?"))))
    return suspeitos


def detectar_devolucao_posterior(notas: list) -> bool:
    """F13: tolerância 10% via faixa, não multiplicação. Antes era impossível casar."""
    vendas: dict = {}
    for n in notas:
        if "VENDA" in str(n.get("natureza", "")).upper():
            cpf = str(n.get("remetente_cpf", ""))
            valor = float(n.get("valor_total", 0))
            vendas.setdefault(cpf, []).append(valor)
    for n in notas:
        if "DEVOLUCAO" in str(n.get("natureza", "")).upper():
            cpf = str(n.get("destinatario_cpf", ""))
            valor_dev = float(n.get("valor_total", 0))
            for v_venda in vendas.get(cpf, []):
                # Devolução parcial entre 50% e 110% da venda original
                if v_venda > 0 and 0.5 * v_venda <= valor_dev <= 1.1 * v_venda:
                    return True
    return False


def detectar_anomalia_temporal(notas: list) -> bool:
    valores = [float(n.get("valor_total", 0)) for n in notas if float(n.get("valor_total", 0)) > 0]
    if len(valores) < 6:
        return False
    media  = float(np.mean(valores))
    desvio = float(np.std(valores))
    if desvio == 0:
        return False
    return sum(1 for v in valores if abs(v - media) > SIGMA_ANOMALIA * desvio) >= 1
