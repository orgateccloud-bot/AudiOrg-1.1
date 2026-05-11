"""Testes unitários do LSTM scorer — modo heurístico (sem modelo PyTorch)."""
from datetime import date, timedelta

from horizon_blue_one.ml.lstm_scorer import (
    JANELA_SEQUENCIA,
    THRESHOLD_LSTM,
    _agrupar_por_produtor,
    _score_heuristico,
    calcular_lstm,
)


def _nota(valor=10000.0, cfop="5101", data="2024-01-15", cnpj="12345678000199"):
    return {"valor_total": valor, "cfop": cfop, "data": data, "remetente_cnpj": cnpj}


def _serie(n=15, valor_base=10000, multiplicador=1.0, cnpj="12345678000199"):
    return [
        _nota(valor=valor_base * (multiplicador ** i),
              data=str(date(2024, 1, 1) + timedelta(days=i * 15)),
              cnpj=cnpj)
        for i in range(n)
    ]


class TestAgruparPorProdutor:
    def test_agrupa_por_cnpj(self):
        notas = [_nota(cnpj="A"), _nota(cnpj="B"), _nota(cnpj="A")]
        grupos = _agrupar_por_produtor(notas)
        assert len(grupos) == 2
        assert len(grupos["A"]) == 2
        assert len(grupos["B"]) == 1

    def test_lista_vazia(self):
        assert _agrupar_por_produtor([]) == {}

    def test_ordem_por_data(self):
        notas = [
            _nota(data="2024-03-01", cnpj="X"),
            _nota(data="2024-01-01", cnpj="X"),
            _nota(data="2024-02-01", cnpj="X"),
        ]
        grupos = _agrupar_por_produtor(notas)
        datas = [n["data"] for n in grupos["X"]]
        assert datas == sorted(datas)


class TestScoreHeuristico:
    def test_serie_estavel_score_baixo(self):
        notas = _serie(15, valor_base=10000, multiplicador=1.0)
        score = _score_heuristico(notas, 10000, 1)
        assert score < THRESHOLD_LSTM

    def test_aceleracao_explosiva_eleva_score(self):
        # Crescimento 3x a cada nota — padrão altamente suspeito
        notas = _serie(15, valor_base=1000, multiplicador=3.0)
        score = _score_heuristico(notas, 100000, 50000)
        assert score > 0.3, f"Score esperado alto por aceleração, obteve {score}"

    def test_menos_de_3_notas_retorna_zero(self):
        assert _score_heuristico([_nota(), _nota()], 10000, 1) == 0.0

    def test_score_entre_zero_e_um(self):
        notas = _serie(20, multiplicador=2.0)
        score = _score_heuristico(notas, 10000, 5000)
        assert 0.0 <= score <= 1.0


class TestCalcularLstm:
    def test_retorno_estrutura_completa(self):
        notas = _serie(10)
        resultado = calcular_lstm(notas)
        assert "modo" in resultado
        assert "score_medio" in resultado
        assert "produtores_anomalos" in resultado
        assert "detalhes" in resultado
        assert resultado["modo"] == "heuristic"

    def test_lista_vazia(self):
        resultado = calcular_lstm([])
        assert resultado["score_medio"] == 0.0
        assert resultado["produtores_anomalos"] == []

    def test_dois_produtores_independentes(self):
        notas = _serie(10, cnpj="PROD_A") + _serie(10, cnpj="PROD_B")
        resultado = calcular_lstm(notas)
        assert "PROD_A" in resultado["detalhes"]
        assert "PROD_B" in resultado["detalhes"]

    def test_score_medio_entre_zero_e_um(self):
        notas = _serie(15, multiplicador=1.5)
        resultado = calcular_lstm(notas)
        assert 0.0 <= resultado["score_medio"] <= 1.0

    def test_produtor_anomalo_detectado(self):
        """Produtor com crescimento explosivo deve ter score alto."""
        notas_normal = _serie(15, valor_base=10000, multiplicador=1.0, cnpj="NORMAL")
        notas_suspeito = _serie(15, valor_base=1000, multiplicador=4.0, cnpj="SUSPEITO")
        resultado = calcular_lstm(notas_normal + notas_suspeito)
        # Score do suspeito deve ser >= normal
        assert resultado["detalhes"].get("SUSPEITO", 0) >= resultado["detalhes"].get("NORMAL", 0)

    def test_constantes_validas(self):
        assert 0 < THRESHOLD_LSTM < 1
        assert JANELA_SEQUENCIA > 0
