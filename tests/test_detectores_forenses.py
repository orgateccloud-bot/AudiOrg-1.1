"""Testes dos detectores forenses — carrossel, smurfing, fantasma, devolução, anomalia."""
from horizon_blue_one.agents.detectores_forenses import (
    detectar_anomalia_temporal,
    detectar_carrossel,
    detectar_devolucao_posterior,
    detectar_fornecedor_fantasma,
    detectar_smurfing,
)

# ── Carrossel ────────────────────────────────────────────────────────────────

class TestCarrossel:
    def test_repete_valores_e_cfop_dominante_detecta(self):
        notas = [
            {"valor_total": 1000.00, "cfop": "5102"},
            {"valor_total": 1000.00, "cfop": "5102"},
            {"valor_total": 1000.00, "cfop": "5102"},
            {"valor_total": 1000.00, "cfop": "5102"},
        ]
        assert detectar_carrossel(notas) is True

    def test_sem_repeticao_significativa(self):
        notas = [
            {"valor_total": 100, "cfop": "5102"},
            {"valor_total": 200, "cfop": "5102"},
            {"valor_total": 300, "cfop": "5102"},
        ]
        assert detectar_carrossel(notas) is False

    def test_valores_repetidos_sem_cfop_dominante_requer_4(self):
        # CFOP variado → precisa 4+ valores repetidos para detectar
        notas = [
            {"valor_total": 100, "cfop": "5102"},
            {"valor_total": 100, "cfop": "1102"},
            {"valor_total": 100, "cfop": "5101"},
            {"valor_total": 100, "cfop": "1101"},
            {"valor_total": 200, "cfop": "5102"},  # 4 valores únicos = 4 grupos
        ]
        # 4x 100 mas com cfop_dom < 85%, precisa 4 valores únicos repetindo
        # Apenas 100 repete 4x — repeticoes==1, mas cfop_dom não atende
        assert detectar_carrossel(notas) is False

    def test_lista_vazia(self):
        assert detectar_carrossel([]) is False


# ── Smurfing ─────────────────────────────────────────────────────────────────

class TestSmurfing:
    def test_5_pequenas_mesma_semana_detecta(self):
        notas = [
            {"valor_total": 5000, "data": "2025-01-06"},  # semana 2 ISO
            {"valor_total": 4000, "data": "2025-01-07"},
            {"valor_total": 6000, "data": "2025-01-08"},
            {"valor_total": 3000, "data": "2025-01-09"},
            {"valor_total": 2000, "data": "2025-01-10"},
        ]
        assert detectar_smurfing(notas) is True

    def test_menos_que_5_pequenas(self):
        notas = [{"valor_total": 100, "data": "2025-01-01"}] * 3
        assert detectar_smurfing(notas) is False

    def test_pequenas_espalhadas_em_semanas_diferentes(self):
        notas = [
            {"valor_total": 100, "data": "2025-01-06"},
            {"valor_total": 100, "data": "2025-02-10"},
            {"valor_total": 100, "data": "2025-03-15"},
            {"valor_total": 100, "data": "2025-04-20"},
            {"valor_total": 100, "data": "2025-05-25"},
        ]
        assert detectar_smurfing(notas) is False

    def test_valor_grande_nao_conta(self):
        notas = [{"valor_total": 50_000, "data": "2025-01-06"}] * 10
        assert detectar_smurfing(notas) is False

    def test_data_invalida_e_ignorada(self):
        notas = [{"valor_total": 100, "data": "data-invalida"}] * 6
        # 6 pequenas com data inválida → nenhuma janela → False
        assert detectar_smurfing(notas) is False


# ── Fornecedor Fantasma ──────────────────────────────────────────────────────

class TestFornecedorFantasma:
    def test_ie_isento_em_venda_destinatario_e_suspeito(self):
        notas = [
            {"natureza": "VENDA", "posicao": "DESTINATARIO",
             "ie_remetente": "ISENTO", "numero": "001"},
        ]
        out = detectar_fornecedor_fantasma(notas)
        assert "001" in out

    def test_ie_vazia_e_suspeita(self):
        notas = [
            {"natureza": "VENDA", "posicao": "DESTINATARIO",
             "ie_remetente": "", "numero": "002"},
        ]
        assert "002" in detectar_fornecedor_fantasma(notas)

    def test_ie_preenchida_nao_suspeita(self):
        notas = [
            {"natureza": "VENDA", "posicao": "DESTINATARIO",
             "ie_remetente": "12345678", "numero": "003"},
        ]
        assert detectar_fornecedor_fantasma(notas) == []

    def test_posicao_remetente_nao_conta(self):
        notas = [
            {"natureza": "VENDA", "posicao": "REMETENTE",
             "ie_remetente": "", "numero": "004"},
        ]
        assert detectar_fornecedor_fantasma(notas) == []


# ── Devolução Posterior ──────────────────────────────────────────────────────

class TestDevolucaoPosterior:
    def test_venda_e_devolucao_compativel(self):
        notas = [
            {"natureza": "VENDA", "remetente_cpf": "111", "valor_total": 1000},
            {"natureza": "DEVOLUCAO", "destinatario_cpf": "111", "valor_total": 950},
        ]
        assert detectar_devolucao_posterior(notas) is True

    def test_sem_devolucao(self):
        notas = [{"natureza": "VENDA", "remetente_cpf": "111", "valor_total": 1000}]
        assert detectar_devolucao_posterior(notas) is False

    def test_devolucao_fora_da_faixa(self):
        notas = [
            {"natureza": "VENDA", "remetente_cpf": "111", "valor_total": 1000},
            {"natureza": "DEVOLUCAO", "destinatario_cpf": "111", "valor_total": 100},  # 10%
        ]
        assert detectar_devolucao_posterior(notas) is False


# ── Anomalia Temporal ────────────────────────────────────────────────────────

class TestAnomaliaTemporal:
    def test_outlier_em_serie_uniforme_detecta(self):
        notas = [
            {"valor_total": 100} for _ in range(6)
        ] + [{"valor_total": 100_000}]
        assert detectar_anomalia_temporal(notas) is True

    def test_menos_que_6_notas(self):
        assert detectar_anomalia_temporal(
            [{"valor_total": 100}] * 3
        ) is False

    def test_serie_uniforme_sem_anomalia(self):
        notas = [{"valor_total": 100} for _ in range(10)]
        # desvio == 0 → return False
        assert detectar_anomalia_temporal(notas) is False

    def test_valor_zero_e_filtrado(self):
        # 5 zeros são filtrados; <6 válidos → False
        notas = [{"valor_total": 0}] * 5 + [{"valor_total": 100}] * 3
        assert detectar_anomalia_temporal(notas) is False
