"""Testes do protocolo @Delta — anonimização de PII (LGPD).

Garante que CPF/CNPJ são redigidos antes de qualquer chamada LLM e que
campos de nome/razão social são substituídos por marcadores opacos.
"""
from horizon_blue_one.core.privacy import (
    RE_CNPJ,
    RE_CPF,
    anonymize_payload,
    anonymize_pii,
)

# ── anonymize_pii (regex puro) ────────────────────────────────────────────────

class TestAnonymizePii:
    def test_cpf_formatado_redigido(self):
        texto = "O CPF é 123.456.789-09 do produtor"
        assert "[CPF_PROTEGIDO]" in anonymize_pii(texto)
        assert "123.456.789-09" not in anonymize_pii(texto)

    def test_cpf_sem_formatacao_redigido(self):
        assert "[CPF_PROTEGIDO]" in anonymize_pii("CPF 12345678909")

    def test_cnpj_formatado_redigido(self):
        texto = "CNPJ 12.345.678/0001-90"
        assert "[CNPJ_PROTEGIDO]" in anonymize_pii(texto)

    def test_cnpj_sem_formatacao_redigido(self):
        assert "[CNPJ_PROTEGIDO]" in anonymize_pii("CNPJ 12345678000190")

    def test_multiplos_cpfs_no_mesmo_texto(self):
        texto = "Produtores: 123.456.789-09 e 987.654.321-00"
        result = anonymize_pii(texto)
        assert result.count("[CPF_PROTEGIDO]") == 2

    def test_texto_sem_pii_inalterado(self):
        texto = "Nota fiscal de venda de gado bovino"
        assert anonymize_pii(texto) == texto

    def test_input_nao_string_retornado_intacto(self):
        assert anonymize_pii(None) is None
        assert anonymize_pii(123) == 123
        assert anonymize_pii([1, 2]) == [1, 2]

    def test_string_vazia(self):
        assert anonymize_pii("") == ""


# ── anonymize_payload (recursivo) ─────────────────────────────────────────────

class TestAnonymizePayload:
    def test_campo_nome_substituido_por_marcador(self):
        payload = {"nome": "João da Silva"}
        out = anonymize_payload(payload)
        assert out["nome"].startswith("[NOME_REDACTED_")
        assert "João" not in out["nome"]

    def test_marcador_preserva_tamanho_original(self):
        payload = {"nome": "Maria"}
        out = anonymize_payload(payload)
        assert out["nome"] == "[NOME_REDACTED_5]"

    def test_razao_social_redigida(self):
        payload = {"razao_social": "Fazenda Boa Vista LTDA"}
        assert "[NOME_REDACTED_" in anonymize_payload(payload)["razao_social"]

    def test_proprietario_redigido(self):
        payload = {"proprietario": "Carlos"}
        assert "[NOME_REDACTED_" in anonymize_payload(payload)["proprietario"]

    def test_cpf_em_string_redigido_recursivamente(self):
        payload = {"observacao": "Produtor CPF 123.456.789-09 autorizado"}
        out = anonymize_payload(payload)
        assert "[CPF_PROTEGIDO]" in out["observacao"]

    def test_dict_aninhado_processado(self):
        payload = {
            "contribuinte": {
                "nome": "João",
                "documento": "CPF 123.456.789-09",
            }
        }
        out = anonymize_payload(payload)
        assert out["contribuinte"]["nome"].startswith("[NOME_REDACTED_")
        assert "[CPF_PROTEGIDO]" in out["contribuinte"]["documento"]

    def test_lista_de_dicts_processada(self):
        payload = {
            "notas": [
                {"remetente_nome": "João", "valor": 1000},
                {"remetente_nome": "Maria", "valor": 2000},
            ]
        }
        out = anonymize_payload(payload)
        assert out["notas"][0]["remetente_nome"].startswith("[NOME_REDACTED_")
        assert out["notas"][1]["remetente_nome"].startswith("[NOME_REDACTED_")
        assert out["notas"][0]["valor"] == 1000  # valor numérico preservado

    def test_lista_com_strings_e_dicts_misturados(self):
        payload = {"itens": ["texto puro", {"nome": "X"}, 42]}
        out = anonymize_payload(payload)
        assert out["itens"][0] == "texto puro"
        assert out["itens"][1]["nome"].startswith("[NOME_REDACTED_")
        assert out["itens"][2] == 42

    def test_valores_numericos_preservados(self):
        payload = {"valor": 1500.50, "quantidade": 10}
        out = anonymize_payload(payload)
        assert out["valor"] == 1500.50
        assert out["quantidade"] == 10

    def test_valores_booleanos_preservados(self):
        payload = {"ativo": True, "suspenso": False}
        out = anonymize_payload(payload)
        assert out["ativo"] is True
        assert out["suspenso"] is False

    def test_none_preservado(self):
        payload = {"observacao": None}
        out = anonymize_payload(payload)
        assert out["observacao"] is None

    def test_campos_neutros_aplicam_apenas_regex(self):
        payload = {"descricao": "Cliente 123.456.789-09 confirmou"}
        out = anonymize_payload(payload)
        assert "[CPF_PROTEGIDO]" in out["descricao"]
        assert out["descricao"] != payload["descricao"]

    def test_payload_vazio(self):
        assert anonymize_payload({}) == {}


# ── Regex (sanity) ────────────────────────────────────────────────────────────

class TestRegex:
    def test_re_cpf_match_formatado(self):
        assert RE_CPF.search("123.456.789-09")

    def test_re_cpf_match_sem_formatacao(self):
        assert RE_CPF.search("12345678909")

    def test_re_cnpj_match_formatado(self):
        assert RE_CNPJ.search("12.345.678/0001-90")

    def test_re_cnpj_match_sem_formatacao(self):
        assert RE_CNPJ.search("12345678000190")

    def test_re_cpf_nao_confunde_numero_curto(self):
        # 12345 não é CPF (precisa de 11 dígitos)
        assert not RE_CPF.search(" 12345 ")
