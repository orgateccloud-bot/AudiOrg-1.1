"""Testes extras do XGBoost scorer — modo treinado, falhas e carregamento."""
from unittest.mock import MagicMock

import numpy as np

from horizon_blue_one.ml import xgboost_scorer as xgb_mod
from horizon_blue_one.ml.xgboost_scorer import (
    FEATURE_COLS_TREINADO,
    _padroes_data,
    _score_heuristico,
    calcular_score,
    calcular_score_com_cache,
)


def _nota(**kw):
    base = {"valor_total": 1000, "cfop": "5102", "data": "2025-01-01",
            "destinatario_cpf": "111", "natureza": "VENDA", "cabecas": 5}
    base.update(kw)
    return base


# ── _score_heuristico ────────────────────────────────────────────────────────

class TestScoreHeuristico:
    def test_features_zero_score_zero(self):
        features = {k: 0.0 for k in xgb_mod.FEATURE_WEIGHTS}
        assert _score_heuristico(features) == 0.0

    def test_features_um_atinge_score_alto(self):
        features = {k: 1.0 for k in xgb_mod.FEATURE_WEIGHTS}
        assert _score_heuristico(features) == 100.0

    def test_padroes_data_sem_datas(self):
        # _padroes_data com lista vazia → 0
        assert _padroes_data([]) == 0.0

    def test_padroes_data_todas_iguais_baixo(self):
        notas = [{"data": "2025-01-01"} for _ in range(5)]
        # 1 data única / 5 = 0.2
        assert _padroes_data(notas) == 0.2


# ── Modo XGBoost treinado ────────────────────────────────────────────────────

class TestModoTreinadoMock:
    def _mock_model(self, prob=0.92):
        m = MagicMock()
        # predict_proba retorna np.array([[1-p, p]])
        m.predict_proba.return_value = np.array([[1 - prob, prob]])
        return m

    def test_calcular_score_usa_xgboost_quando_modelo_disponivel(self, monkeypatch):
        m = self._mock_model(prob=0.87)
        monkeypatch.setattr(xgb_mod, "_xgb_model", m)
        monkeypatch.setattr(xgb_mod, "_xgb_model_version", "v-test")
        notas = [_nota() for _ in range(5)]
        out = calcular_score(notas)
        assert out["modo"] == "xgboost_treinado"
        assert out["score"] == 87.0
        assert out["model_version"] == "v-test"

    def test_calcular_score_falha_xgboost_cai_para_heuristico(self, monkeypatch):
        m = MagicMock()
        m.predict_proba.side_effect = RuntimeError("modelo quebrado")
        monkeypatch.setattr(xgb_mod, "_xgb_model", m)
        notas = [_nota() for _ in range(3)]
        out = calcular_score(notas)
        assert out["modo"] == "heuristico"

    def test_calcular_score_com_cache_xgboost_branch(self, monkeypatch):
        m = self._mock_model(prob=0.55)
        monkeypatch.setattr(xgb_mod, "_xgb_model", m)
        notas = [_nota()]
        det = {
            "carrossel": True, "smurfing": False,
            "fornecedor_fantasma": ["X"], "devolucao_posterior": False,
            "anomalia_temporal": True,
        }
        out = calcular_score_com_cache(notas, det)
        assert out["modo"] == "xgboost_treinado"
        assert out["score"] == 55.0
        # tipologias_criticas conta: carrossel(1) + fantasma(1) + anomalia(1) = 3
        assert out["tipologias_criticas"] == 3

    def test_calcular_score_com_cache_falha_xgboost_cai_para_heuristico(self, monkeypatch):
        m = MagicMock()
        m.predict_proba.side_effect = ValueError("modelo inválido")
        monkeypatch.setattr(xgb_mod, "_xgb_model", m)
        notas = [_nota()]
        det = {
            "carrossel": False, "smurfing": False,
            "fornecedor_fantasma": [], "devolucao_posterior": False,
            "anomalia_temporal": False,
        }
        out = calcular_score_com_cache(notas, det)
        assert out["modo"] == "heuristico"


# ── _try_load_model — caminhos não-felizes ───────────────────────────────────

class TestTryLoadModel:
    def test_path_nao_existe_nao_carrega(self, monkeypatch):
        # Re-inicia o estado do loader
        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", False)
        monkeypatch.setattr(xgb_mod, "_xgb_model", None)
        monkeypatch.setenv("XGBOOST_MODEL_PATH", "/path/que/nao/existe.json")
        xgb_mod._try_load_model()
        assert xgb_mod._xgb_model is None

    def test_path_vazio_nao_carrega(self, monkeypatch):
        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", False)
        monkeypatch.setattr(xgb_mod, "_xgb_model", None)
        monkeypatch.delenv("XGBOOST_MODEL_PATH", raising=False)
        xgb_mod._try_load_model()
        assert xgb_mod._xgb_model is None

    def test_carga_falha_captura_excecao(self, tmp_path, monkeypatch):
        modelo_falso = tmp_path / "fake.json"
        modelo_falso.write_text("isso não é um modelo XGBoost")
        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", False)
        monkeypatch.setattr(xgb_mod, "_xgb_model", None)
        monkeypatch.setenv("XGBOOST_MODEL_PATH", str(modelo_falso))
        # Não deve levantar
        xgb_mod._try_load_model()
        assert xgb_mod._xgb_model is None
        assert xgb_mod._xgb_model_version == "heuristic"

    def test_already_attempted_retorna_early(self, monkeypatch):
        """Segunda chamada ao loader é early-return (cobre L57)."""
        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", True)
        # Mesmo com env apontando para arquivo válido, não tenta carregar
        chamou = []
        monkeypatch.setattr("os.path.exists", lambda _p: chamou.append(_p) or True)
        xgb_mod._try_load_model()
        assert chamou == []  # nunca chegou no exists()

    def test_carga_sucesso_seta_modelo_e_version(self, tmp_path, monkeypatch):
        """Cobre L65-69: modelo carrega ok, version=hash do arquivo."""
        modelo = tmp_path / "ok.json"
        modelo.write_bytes(b"binario-modelo-fake")

        monkeypatch.setattr(xgb_mod, "_xgb_load_attempted", False)
        monkeypatch.setattr(xgb_mod, "_xgb_model", None)
        monkeypatch.setenv("XGBOOST_MODEL_PATH", str(modelo))

        # Mocka xgb.XGBClassifier para não exigir xgboost real
        import sys
        import types
        fake_xgb_mod = types.ModuleType("xgboost")
        class _FakeClassifier:
            def load_model(self, p):
                pass
        fake_xgb_mod.XGBClassifier = _FakeClassifier
        monkeypatch.setitem(sys.modules, "xgboost", fake_xgb_mod)

        xgb_mod._try_load_model()
        assert xgb_mod._xgb_model is not None
        # Version é hash truncado (12 chars hex)
        assert len(xgb_mod._xgb_model_version) == 12


class TestConcentracaoVazia:
    def test_concentracao_lista_vazia(self):
        from horizon_blue_one.ml.xgboost_scorer import _concentracao
        # destinos vazio retorna 0.0 (cobre L125)
        assert _concentracao([]) == 0.0


# ── FEATURE_COLS_TREINADO sanidade ───────────────────────────────────────────

class TestFeatureCols:
    def test_lista_tem_13_colunas(self):
        # 8 base + 5 flags = 13
        assert len(FEATURE_COLS_TREINADO) == 13

    def test_flags_no_final(self):
        for flag in ("flag_carrossel", "flag_smurfing", "flag_fantasma",
                     "flag_devolucao", "flag_anomalia"):
            assert flag in FEATURE_COLS_TREINADO
