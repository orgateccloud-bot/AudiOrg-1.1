"""Testes do precalc — camada determinística paralela."""
import pytest

from horizon_blue_one.core.precalc import (
    _caixa_aggregator,
    _cfop_validator,
    _doc_validator,
    _grafo_metrics,
    _itr_capacidade,
    _lcdpr_diff,
    _lstm_score,
    _payload_hash,
    _pii_scanner,
    _re1_classifier,
    _xgboost_score,
    precalcular,
)

# ── Componentes individuais ──────────────────────────────────────────────────

class TestRE1Classifier:
    def test_aplica_re1_em_cada_nota(self):
        notas = [
            {"natureza": "VENDA", "posicao": "DESTINATARIO",
             "atividade": "bovino", "tipo_doc": "nfa-e", "valor_total": 1000},
        ]
        out = _re1_classifier(notas)
        assert out[0]["regra_aplicada"] == "REGRA_ESPECIAL_1"

    def test_nao_muta_lista_original(self):
        original = [{"natureza": "VENDA", "posicao": "REMETENTE",
                     "atividade": "bovino", "tipo_doc": "nfa-e"}]
        _re1_classifier(original)
        # Função original muta in-place; clone antes preserva chave nova
        assert "regra_aplicada" not in original[0]


class TestPiiScanner:
    def test_detecta_cpf_e_cnpj(self):
        notas = [
            {"remetente_cpf": "123.456.789-09"},
            {"destinatario_cpf": "98.765.432/0001-10"},
        ]
        out = _pii_scanner(notas)
        assert out["cpfs_detectados"] >= 1
        assert out["cnpjs_detectados"] >= 1
        assert out["total_pii"] >= 2

    def test_sem_pii_retorna_zero(self):
        out = _pii_scanner([{"valor": 100, "natureza": "VENDA"}])
        assert out["total_pii"] == 0


class TestDocValidator:
    def test_chave_invalida_gera_pendencia(self):
        notas = [{"chave_acesso": "curta", "data": "2025-01-01", "numero": "1"}]
        out = _doc_validator(notas, {})
        assert out["total_pendencias"] >= 1
        assert any("chave" in p for p in out["pendencias"])

    def test_sem_data_gera_pendencia(self):
        notas = [{"chave_acesso": "X" * 44, "numero": "1"}]
        out = _doc_validator(notas, {})
        assert any("sem_data" in p for p in out["pendencias"])

    def test_ie_isento_invalido(self):
        out = _doc_validator([], {"inscricao_estadual": "ISENTO"})
        assert out["ie_valida"] is False

    def test_ie_preenchida_valida(self):
        out = _doc_validator([], {"inscricao_estadual": "12345"})
        assert out["ie_valida"] is True


class TestCfopValidator:
    def test_cfop_5102_valido(self):
        out = _cfop_validator([{"cfop": "5102", "numero": "1"}])
        assert out["validos"] == 1
        assert out["total_divergencias"] == 0

    def test_cfop_invalido_lista_divergencia(self):
        out = _cfop_validator([{"cfop": "9999", "numero": "1"}])
        assert out["total_divergencias"] == 1
        assert out["divergentes"][0]["cfop"] == "9999"

    def test_total_corresponde_quantidade_de_notas(self):
        out = _cfop_validator([{"cfop": "5102"}, {"cfop": "1102"}])
        assert out["total"] == 2


class TestLcdprDiff:
    def test_conforme_quando_receitas_batem(self):
        notas = [{"valor_total": 1000, "categoria_contabil": "RECEITA"}]
        out = _lcdpr_diff(notas, {"total_receitas": 1000})
        assert out["status_conformidade"] == "CONFORME"
        assert abs(out["divergencia"]) < 0.01

    def test_critico_acima_50k(self):
        notas = [{"valor_total": 100_000, "categoria_contabil": "RECEITA"}]
        out = _lcdpr_diff(notas, {"total_receitas": 0})
        assert out["status_conformidade"] == "CRITICO"

    def test_divergente_intermediario(self):
        notas = [{"valor_total": 5000, "categoria_contabil": "RECEITA"}]
        out = _lcdpr_diff(notas, {"total_receitas": 0})
        assert out["status_conformidade"] == "DIVERGENTE"


class TestItrCapacidade:
    def test_subutilizado_quando_gu_baixo(self):
        out = _itr_capacidade({"area_total_ha": 100, "area_utilizada_ha": 50})
        assert out["gu_pct"] == 50.0
        assert out["subutilizado"] is True

    def test_nao_subutilizado_quando_gu_alto(self):
        out = _itr_capacidade({"area_total_ha": 100, "area_utilizada_ha": 90})
        assert out["subutilizado"] is False

    def test_area_zero_nao_quebra(self):
        out = _itr_capacidade({"area_total_ha": 0, "area_utilizada_ha": 0})
        assert out["gu_pct"] == 0
        assert out["subutilizado"] is False


class TestCaixaAggregator:
    def test_separa_receita_e_despesa(self):
        notas = [
            {"valor_total": 1000, "categoria_contabil": "RECEITA"},
            {"valor_total": 300, "categoria_contabil": "DESPESA"},
            {"valor_total": 100, "categoria_contabil": "CUSTO"},
        ]
        out = _caixa_aggregator(notas)
        assert out["entradas"] == 1000
        assert out["saidas"] == 400
        assert out["saldo"] == 600

    def test_sem_categoria_ignora(self):
        out = _caixa_aggregator([{"valor_total": 500}])
        assert out["entradas"] == 0
        assert out["saidas"] == 0


class TestGrafoMetrics:
    def test_grafo_com_arestas_calcula_densidade(self):
        notas = [
            {"remetente_cpf": "111", "destinatario_cpf": "222", "valor_total": 100},
            {"remetente_cpf": "222", "destinatario_cpf": "333", "valor_total": 200},
        ]
        out = _grafo_metrics(notas)
        # Pode retornar disponivel=False se networkx ausente
        if out.get("disponivel"):
            assert out["nos"] >= 2

    def test_poucos_nos_retorna_zero(self):
        out = _grafo_metrics([])
        # Sem networkx → disponivel=False; com networkx → grafo vazio
        assert out["ciclos"] == 0


class TestXgboostScore:
    def test_score_baixo_sem_detectores(self):
        det = {"carrossel": False, "smurfing": False,
               "fornecedor_fantasma": [], "devolucao_posterior": False,
               "anomalia_temporal": False}
        out = _xgboost_score([], det)
        assert "score" in out
        assert out["score"] >= 0

    def test_retorna_campos_canonicos(self):
        det = {"carrossel": True, "smurfing": False,
               "fornecedor_fantasma": [], "devolucao_posterior": False,
               "anomalia_temporal": False}
        notas = [{"valor_total": 1000, "natureza": "VENDA", "cfop": "5102"}]
        out = _xgboost_score(notas, det)
        assert "score" in out
        assert "probabilidade_autuacao" in out
        assert "tipologias_criticas" in out
        assert out["tipologias_criticas"] >= 1  # carrossel ativo


class TestLstmScore:
    def test_modo_heuristic_sem_modelo(self):
        out = _lstm_score([])
        assert "modo" in out
        assert "score_medio" in out


class TestPayloadHash:
    def test_hash_estavel(self):
        p = {"notas": [{"x": 1}], "contribuinte": {"cpf": "1"}}
        assert _payload_hash(p) == _payload_hash(p)

    def test_hash_diferente_para_payloads_distintos(self):
        h1 = _payload_hash({"notas": [{"x": 1}]})
        h2 = _payload_hash({"notas": [{"x": 2}]})
        assert h1 != h2

    def test_hash_tem_16_chars(self):
        assert len(_payload_hash({})) == 16


# ── Integração: precalcular() ────────────────────────────────────────────────

class TestPrecalcular:
    @pytest.mark.asyncio
    async def test_payload_vazio_retorna_estrutura_completa(self):
        payload = {"notas": [], "contribuinte": {}, "lcdpr_data": {}}
        out = await precalcular(payload)
        pre = out["__precalc__"]
        # Todas as chaves principais presentes
        for chave in ("notas_re1", "pii", "documentos", "detectores",
                      "xgboost", "lstm", "cfop", "lcdpr", "itr", "caixa"):
            assert chave in pre, f"chave ausente: {chave}"

    @pytest.mark.asyncio
    async def test_idempotente_se_precalc_ja_existe(self):
        marker = {"valor": "ja-calculado"}
        payload = {"notas": [], "__precalc__": marker}
        out = await precalcular(payload)
        assert out["__precalc__"] is marker

    @pytest.mark.asyncio
    async def test_aplica_re1_em_notas_destinatario_rural(self):
        payload = {
            "notas": [{
                "natureza": "VENDA", "posicao": "DESTINATARIO",
                "atividade": "bovino", "tipo_doc": "nfa-e",
                "valor_total": 5000, "chave_acesso": "X" * 44, "data": "2025-01-01",
            }],
            "contribuinte": {"area_total_ha": 100, "area_utilizada_ha": 80},
            "lcdpr_data": {},
        }
        out = await precalcular(payload)
        notas_re1 = out["__precalc__"]["notas_re1"]
        assert notas_re1[0]["regra_aplicada"] == "REGRA_ESPECIAL_1"


# ── Fallback do _xgboost_score quando scorer não tem API com cache ───────────

class TestXgboostScoreFallback:
    def test_fallback_quando_calcular_score_com_cache_ausente(self, monkeypatch):
        """Se calcular_score_com_cache falha import, usa heurística inline."""
        import horizon_blue_one.ml.xgboost_scorer as xgb_mod

        # Remove o atributo para forçar AttributeError no import explícito
        original = xgb_mod.calcular_score_com_cache
        try:
            delattr(xgb_mod, "calcular_score_com_cache")
            detectores = {
                "carrossel": True, "smurfing": True,
                "fornecedor_fantasma": ["X", "Y"], "devolucao_posterior": True,
                "anomalia_temporal": True,
            }
            out = _xgboost_score([], detectores)
            # Heurística inline soma 25+20+15+15+10 = 85 + 2*2 = 89
            assert out["score"] >= 80
            assert out["tipologias_criticas"] == 5
        finally:
            xgb_mod.calcular_score_com_cache = original


# ── _lstm_score com erro capturado ───────────────────────────────────────────

class TestLstmScoreErro:
    def test_excecao_no_lstm_retorna_modo_erro(self, monkeypatch):
        from horizon_blue_one.core import precalc as pre_mod

        def boom(_notas):
            raise RuntimeError("modelo lstm quebrou")

        monkeypatch.setattr(pre_mod, "calcular_lstm", boom)
        out = _lstm_score([{"valor_total": 100}])
        assert out["modo"] == "erro"
        assert out["score_medio"] == 0.0


# ── _grafo_metrics sem networkx (ImportError) ────────────────────────────────

class TestGrafoMetricsSemNetworkX:
    def test_sem_networkx_retorna_estrutura_vazia(self, monkeypatch):
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "networkx":
                raise ImportError("networkx ausente")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        out = _grafo_metrics([{"remetente_cpf": "A", "destinatario_cpf": "B"}])
        assert out["disponivel"] is False
        assert out["densidade"] == 0


class TestGrafoMetricsSimpleCyclesFalha:
    def test_simple_cycles_excecao_zera_ciclos(self, monkeypatch):
        try:
            import networkx as nx
        except ImportError:
            pytest.skip("networkx não instalado")

        def boom(g):
            raise RuntimeError("simple_cycles falhou")

        monkeypatch.setattr(nx, "simple_cycles", boom)
        notas = [
            {"remetente_cpf": "A", "destinatario_cpf": "B", "valor_total": 100},
            {"remetente_cpf": "B", "destinatario_cpf": "A", "valor_total": 50},
        ]
        out = _grafo_metrics(notas)
        assert out["ciclos"] == 0
        assert out["disponivel"] is True


# ── Memo cache hit + limpeza de entradas expiradas ───────────────────────────

class TestMemoCache:
    @pytest.mark.asyncio
    async def test_memo_hit_reusa_resultado(self, monkeypatch):
        from horizon_blue_one.core import precalc as pre_mod

        # Reset cache
        pre_mod._MEMO_CACHE.clear()

        payload1 = {
            "notas": [{"valor_total": 100, "cfop": "5102"}],
            "contribuinte": {"cpf": "111"},
            "lcdpr_data": {},
        }
        await precalcular(payload1)

        # Segunda chamada com payload equivalente → memo hit
        payload2 = {
            "notas": [{"valor_total": 100, "cfop": "5102"}],
            "contribuinte": {"cpf": "111"},
            "lcdpr_data": {},
        }
        out = await precalcular(payload2)
        # Deve preencher notas_classificadas via cache hit
        assert "notas_classificadas" in out
        assert "__precalc__" in out

    @pytest.mark.asyncio
    async def test_limpeza_de_entradas_expiradas(self, monkeypatch):
        from horizon_blue_one.core import precalc as pre_mod

        pre_mod._MEMO_CACHE.clear()
        # Insere 257 entradas expiradas (acima do threshold de 256 + idade > TTL)
        past = 0.0  # tempo Epoch zero, muito antigo
        for i in range(257):
            pre_mod._MEMO_CACHE[f"hash{i}"] = (past, {"notas_re1": []})

        # Agora chama precalcular para disparar limpeza
        payload = {
            "notas": [], "contribuinte": {"unique": "cleanup-test"}, "lcdpr_data": {},
        }
        await precalcular(payload)
        # Entradas expiradas devem ter sido removidas
        assert all(not k.startswith("hash") for k in pre_mod._MEMO_CACHE.keys())
