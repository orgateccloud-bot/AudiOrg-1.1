"""Testes de validação CPF/CNPJ na API de auditoria."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_val.db")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-validacao")
    os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
    from api.main import app
    return TestClient(app)


def _payload_base(cpf="012.345.678-90"):
    return {
        "contribuinte_cpf": cpf,
        "contribuinte_nome": "Produtor Teste",
        "notas": [{
            "numero": "001",
            "data": "2024-01-15",
            "natureza": "VENDA",
            "valor_total": 10000.0,
        }]
    }


class TestValidacaoCpfCnpj:
    def test_cpf_valido_aceito(self, client):
        """CPF com dígitos verificadores corretos não deve retornar 422 por CPF."""
        with patch("api.services.auditoria.processar_nfae",
                   new=AsyncMock(return_value={"score": 0})):
            resp = client.post("/auditoria/nfae", json=_payload_base("012.345.678-90"))
        assert resp.status_code != 422 or "CPF" not in resp.text

    def test_string_aleatoria_rejeitada(self, client):
        resp = client.post("/auditoria/nfae", json=_payload_base("nao_e_um_cpf"))
        assert resp.status_code == 422

    def test_cpf_com_digitos_errados_rejeitado(self, client):
        resp = client.post("/auditoria/nfae", json=_payload_base("111.111.111-11"))
        assert resp.status_code == 422

    def test_cpf_curto_rejeitado(self, client):
        resp = client.post("/auditoria/nfae", json=_payload_base("12345"))
        assert resp.status_code == 422

    def test_notas_vazias_rejeitadas(self, client):
        payload = _payload_base()
        payload["notas"] = []
        resp = client.post("/auditoria/nfae", json=payload)
        assert resp.status_code == 422

    def test_valor_negativo_rejeitado(self, client):
        payload = _payload_base()
        payload["notas"][0]["valor_total"] = -100
        resp = client.post("/auditoria/nfae", json=payload)
        assert resp.status_code == 422

    def test_data_formato_invalido_rejeitado(self, client):
        payload = _payload_base()
        payload["notas"][0]["data"] = "15/01/2024"  # formato errado
        resp = client.post("/auditoria/nfae", json=payload)
        assert resp.status_code == 422

    def test_nome_vazio_rejeitado(self, client):
        payload = _payload_base()
        payload["contribuinte_nome"] = ""
        resp = client.post("/auditoria/nfae", json=payload)
        assert resp.status_code == 422


class TestValidacaoInterna:
    """Testa funções de validação diretamente sem HTTP."""

    def test_cpf_valido(self):
        from api.routes.auditoria import _validar_cpf
        assert _validar_cpf("012.345.678-90") is True

    def test_cpf_invalido(self):
        from api.routes.auditoria import _validar_cpf
        assert _validar_cpf("111.111.111-11") is False
        assert _validar_cpf("000.000.000-00") is False

    def test_cnpj_valido(self):
        from api.routes.auditoria import _validar_cnpj
        assert _validar_cnpj("11.222.333/0001-81") is True

    def test_cnpj_invalido(self):
        from api.routes.auditoria import _validar_cnpj
        assert _validar_cnpj("11.111.111/1111-11") is False

    def test_cpf_so_digitos(self):
        from api.routes.auditoria import _validar_cpf
        assert _validar_cpf("01234567890") is True
