"""Testes unitários do XGBoost scorer — modo heurístico (sem modelo treinado)."""
import pytest
from horizon_blue_one.ml.xgboost_scorer import (
    calcular_score,
    extrair_features,
    FEATURE_WEIGHTS,
)


def _nota(valor=10000.0, cfop="5101", natureza="VENDA", data="2024-01-15",
          destinatario_cpf="", cabecas=10):
    return {
        "valor_total": valor,
        "cfop": cfop,
        "natureza": natureza,
        "data": data,
        "destinatario_cpf": destinatario_cpf,
        "cabecas": cabecas,
    }


class TestExtrairFeatures:
    def test_lista_vazia_retorna_zeros(self):
        feats = extrair_features([])
        assert all(v == 0.0 for v in feats.values())
        assert set(feats.keys()) == set(FEATURE_WEIGHTS.keys())

    def test_nota_unica_sem_variacao(self):
        feats = extrair_features([_nota(valor=5000)])
        assert feats["variacao_preco"] == 0.0
        assert feats["freq_devolucoes"] == 0.0

    def test_concentracao_destinatario_unico(self):
        notas = [_nota(destinatario_cpf="12345678901") for _ in range(5)]
        feats = extrair_features(notas)
        assert feats["concentracao_dest"] == 1.0

    def test_proporcao_pf_com_cpf_formatado(self):
        notas = [_nota(destinatario_cpf="123.456.789-01") for _ in range(4)]
        feats = extrair_features(notas)
        assert feats["proporcao_pf"] == 1.0

    def test_devolucao_detectada(self):
        notas = [_nota(natureza="devolucao de gado"), _nota(), _nota()]
        feats = extrair_features(notas)
        assert feats["freq_devolucoes"] > 0.0

    def test_variacao_cfop_alta(self):
        notas = [_nota(cfop=str(c)) for c in range(10)]
        feats = extrair_features(notas)
        assert feats["consistencia_cfop"] > 0.5


class TestCalcularScore:
    def test_notas_limpas_score_baixo(self):
        notas = [_nota(valor=10_000, cfop="5101") for _ in range(5)]
        resultado = calcular_score(notas)
        assert resultado["score"] < 40
        assert resultado["nivel"] in ("BAIXO", "MÉDIO", "MEDIO")

    def test_score_estrutura_completa(self):
        notas = [_nota()]
        resultado = calcular_score(notas)
        assert "score" in resultado
        assert "nivel" in resultado
        assert "modo" in resultado
        assert 0 <= resultado["score"] <= 100

    def test_lista_vazia_score_zero(self):
        resultado = calcular_score([])
        assert resultado["score"] == 0.0

    def test_score_maximo_nao_excede_100(self):
        # Notas com todos os flags suspeitos
        notas = []
        for i in range(20):
            notas.append({
                "valor_total": 500 if i % 2 == 0 else 500,  # smurfing + repetição
                "cfop": "5101",
                "natureza": "devolucao" if i % 3 == 0 else "VENDA",
                "data": f"2024-01-{(i % 7) + 1:02d}",
                "destinatario_cpf": "111.111.111-11",
                "cabecas": 1,
                "ie_remetente": "",
                "posicao": "DESTINATARIO",
            })
        resultado = calcular_score(notas)
        assert resultado["score"] <= 100.0

    def test_score_com_detectores_externos(self):
        """calcular_score_com_cache aceita detectores pré-computados."""
        from horizon_blue_one.ml.xgboost_scorer import calcular_score_com_cache
        notas = [_nota()]
        detectores = {
            "carrossel": True,
            "smurfing": False,
            "fornecedor_fantasma": [],
            "devolucao_posterior": False,
            "anomalia_temporal": False,
        }
        resultado = calcular_score_com_cache(notas, detectores)
        assert resultado["score"] > 0
        assert "tipologias_criticas" in resultado
