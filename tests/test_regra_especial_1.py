"""Testes da Regra Especial 1 — reclassificação VENDA→COMPRA para produtor rural DESTINATÁRIO.

Base legal: NBC TG 16 (Estoques) + NBC TG 25 (Estimativas) + Lei 9.250/1995.
Aprovada por: Robson Alain Veloso — CRC-GO | Warley Veloso — CTO.

Regra: nfa-e + natureza VENDA + posicao DESTINATARIO + atividade rural
       → reclassifica como COMPRA/DESPESA com efeito_irpf SUBTRAI.
"""
from horizon_blue_one.orgaudi.regra_especial_1 import (
    ATIVIDADES_RURAIS,
    aplicar_regra_especial_1,
)


def _nota_base(**override):
    base = {
        "natureza": "VENDA",
        "posicao": "DESTINATARIO",
        "atividade": "bovino",
        "tipo_doc": "nfa-e",
        "valor_total": 10_000,
    }
    base.update(override)
    return base


# ── Casos onde a regra SE APLICA ──────────────────────────────────────────────

class TestRE1Aplica:
    def test_reclassifica_venda_destinatario_rural_para_compra(self):
        nota = aplicar_regra_especial_1(_nota_base())
        assert nota["natureza_exibicao"] == "COMPRA"
        assert nota["categoria_contabil"] == "DESPESA"
        assert nota["efeito_irpf"] == "SUBTRAI"
        assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"

    def test_atribui_contas_contabeis_corretas(self):
        nota = aplicar_regra_especial_1(_nota_base())
        assert nota["conta_debito"] == "1.1.2.01"   # Gado em Rebanho
        assert nota["conta_credito"] == "2.1.1.1.01"  # Fornecedores

    def test_confianca_alta_em_valor_normal(self):
        nota = aplicar_regra_especial_1(_nota_base(valor_total=50_000))
        assert nota["confianca"] == 0.99
        assert nota["alertas_re1"] == []

    def test_alerta_valor_acima_500k(self):
        nota = aplicar_regra_especial_1(_nota_base(valor_total=600_000))
        assert any("R$500k" in a for a in nota["alertas_re1"])
        assert nota["confianca"] == 0.75

    def test_alerta_valor_abaixo_100(self):
        nota = aplicar_regra_especial_1(_nota_base(valor_total=50))
        assert any("R$100" in a for a in nota["alertas_re1"])
        assert nota["confianca"] == 0.75

    def test_aplica_para_varias_atividades_rurais(self):
        for atividade in ("bovino", "soja", "milho", "suíno", "cana", "café"):
            nota = aplicar_regra_especial_1(_nota_base(atividade=atividade))
            assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1", \
                f"falhou para atividade={atividade}"

    def test_atividade_case_insensitive(self):
        nota = aplicar_regra_especial_1(_nota_base(atividade="BOVINO"))
        assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"

    def test_posicao_destinatario_abreviada(self):
        # Aceita qualquer string contendo "DESTIN"
        nota = aplicar_regra_especial_1(_nota_base(posicao="DESTIN"))
        assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"


# ── Casos onde a regra NÃO se aplica ──────────────────────────────────────────

class TestRE1NaoAplica:
    def test_natureza_diferente_de_venda(self):
        nota = aplicar_regra_especial_1(_nota_base(natureza="REMESSA"))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"
        assert nota["categoria_contabil"] == "REMESSA"
        assert nota["efeito_irpf"] == "NEUTRO"

    def test_produtor_como_remetente(self):
        # Produtor vendendo é o caso normal — SOMA na receita
        nota = aplicar_regra_especial_1(_nota_base(posicao="REMETENTE"))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"
        assert nota["categoria_contabil"] == "RECEITA"
        assert nota["efeito_irpf"] == "SOMA"

    def test_atividade_nao_rural(self):
        nota = aplicar_regra_especial_1(_nota_base(atividade="comercio"))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"

    def test_tipo_doc_nao_nfa(self):
        nota = aplicar_regra_especial_1(_nota_base(tipo_doc="nfe"))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"

    def test_atividade_vazia(self):
        nota = aplicar_regra_especial_1(_nota_base(atividade=""))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"

    def test_natureza_vazia(self):
        nota = aplicar_regra_especial_1(_nota_base(natureza=""))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"


# ── Robustez ──────────────────────────────────────────────────────────────────

class TestRE1Robustez:
    def test_nota_sem_campos_opcionais_nao_quebra(self):
        nota = aplicar_regra_especial_1({})
        # Sem natureza/posicao/atividade → não aplica
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"
        assert "alertas_re1" in nota

    def test_valor_total_string_numerica(self):
        # float() lida com string
        nota = aplicar_regra_especial_1(_nota_base(valor_total="100000"))
        assert nota["regra_aplicada"] == "REGRA_ESPECIAL_1"

    def test_natureza_none_tratada(self):
        nota = aplicar_regra_especial_1(_nota_base(natureza=None))
        assert nota["regra_aplicada"] == "CLASSIFICACAO_NORMAL"

    def test_retorna_mesma_referencia_de_dict(self):
        original = _nota_base()
        result = aplicar_regra_especial_1(original)
        assert result is original  # mutação in-place

    def test_alertas_re1_sempre_presente(self):
        for caso in (_nota_base(), _nota_base(natureza="REMESSA"),
                     _nota_base(posicao="REMETENTE")):
            nota = aplicar_regra_especial_1(caso)
            assert "alertas_re1" in nota
            assert isinstance(nota["alertas_re1"], list)

    def test_confianca_sempre_presente(self):
        for caso in (_nota_base(), _nota_base(natureza="REMESSA")):
            nota = aplicar_regra_especial_1(caso)
            assert "confianca" in nota
            assert 0.0 <= nota["confianca"] <= 1.0


class TestAtividadesRurais:
    def test_conjunto_nao_vazio(self):
        assert len(ATIVIDADES_RURAIS) > 5

    def test_inclui_atividades_pecuaria(self):
        assert "bovino" in ATIVIDADES_RURAIS
        assert "ovino" in ATIVIDADES_RURAIS
        assert "equino" in ATIVIDADES_RURAIS

    def test_inclui_agricultura(self):
        assert "soja" in ATIVIDADES_RURAIS
        assert "milho" in ATIVIDADES_RURAIS
