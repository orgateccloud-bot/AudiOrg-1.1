"""Testes dos schemas Pydantic — clientes, auditoria, usuários."""
import io

import pytest
from fastapi import UploadFile
from pydantic import ValidationError

from api.schemas.auditoria import (
    EXTENSOES_ACEITAS,
    TAMANHO_MAX,
    ArquivoUpload,
    UploadAuditoriaParams,
    validar_arquivos,
)
from api.schemas.clientes import (
    ClienteCreate,
    ClienteListResponse,
    ClienteResponse,
    ClienteUpdate,
    _validar_cnpj,
    _validar_cpf,
)
from api.schemas.usuarios import (
    LoginRequest,
    MeResponse,
    SenhaUpdate,
    TokenResponse,
    UsuarioResponse,
)

# ── CPF/CNPJ helpers ─────────────────────────────────────────────────────────

class TestValidadoresCpfCnpj:
    def test_cpf_valido(self):
        # CPF gerado: 529.982.247-25
        assert _validar_cpf("52998224725") is True

    def test_cpf_invalido_dv(self):
        assert _validar_cpf("52998224700") is False

    def test_cpf_todos_digitos_iguais(self):
        assert _validar_cpf("11111111111") is False

    def test_cpf_tamanho_incorreto(self):
        assert _validar_cpf("123") is False

    def test_cnpj_valido(self):
        # CNPJ gerado: 11.222.333/0001-81
        assert _validar_cnpj("11222333000181") is True

    def test_cnpj_invalido_dv(self):
        assert _validar_cnpj("11222333000100") is False

    def test_cnpj_todos_iguais(self):
        assert _validar_cnpj("11111111111111") is False

    def test_cnpj_tamanho_incorreto(self):
        assert _validar_cnpj("123") is False


# ── ClienteCreate / Update ───────────────────────────────────────────────────

class TestClienteCreate:
    def test_cpf_valido_normaliza_para_digitos(self):
        c = ClienteCreate(nome="Joao", cpf_cnpj="529.982.247-25")
        assert c.cpf_cnpj == "52998224725"

    def test_cnpj_valido_normaliza(self):
        c = ClienteCreate(nome="Empresa", cpf_cnpj="11.222.333/0001-81")
        assert c.cpf_cnpj == "11222333000181"

    def test_cpf_invalido_levanta(self):
        with pytest.raises(ValidationError, match="CPF inválido"):
            ClienteCreate(nome="X", cpf_cnpj="12345678900")

    def test_cnpj_invalido_levanta(self):
        with pytest.raises(ValidationError, match="CNPJ inválido"):
            ClienteCreate(nome="X", cpf_cnpj="11222333000100")

    def test_tamanho_intermediario_levanta(self):
        with pytest.raises(ValidationError, match="11 dígitos"):
            ClienteCreate(nome="X", cpf_cnpj="123456")

    def test_nome_strip(self):
        c = ClienteCreate(nome="  Joao  ", cpf_cnpj="52998224725")
        assert c.nome == "Joao"


class TestClienteUpdate:
    def test_aceita_none(self):
        u = ClienteUpdate(nome=None, cpf_cnpj=None)
        assert u.nome is None
        assert u.cpf_cnpj is None

    def test_atualiza_apenas_nome(self):
        u = ClienteUpdate(nome="Novo")
        assert u.nome == "Novo"

    def test_cpf_invalido_em_update_levanta(self):
        with pytest.raises(ValidationError):
            ClienteUpdate(cpf_cnpj="00000000000")

    def test_cnpj_valido_em_update(self):
        u = ClienteUpdate(cpf_cnpj="11.222.333/0001-81")
        assert u.cpf_cnpj == "11222333000181"

    def test_tamanho_intermediario_em_update_levanta(self):
        with pytest.raises(ValidationError):
            ClienteUpdate(cpf_cnpj="12345")


class TestClienteResponses:
    def test_response_aceita_dados(self):
        r = ClienteResponse(id=1, nome="X", cpf_cnpj="52998224725")
        assert r.id == 1

    def test_list_response(self):
        lr = ClienteListResponse(
            items=[ClienteResponse(id=1, nome="X", cpf_cnpj="52998224725")],
            total=1,
        )
        assert lr.total == 1


# ── ArquivoUpload + validar_arquivos ─────────────────────────────────────────

class TestArquivoUpload:
    def test_pdf_valido(self):
        a = ArquivoUpload(nome="doc.pdf", tamanho=1024, content_type="application/pdf")
        assert a.nome == "doc.pdf"

    def test_xml_valido(self):
        a = ArquivoUpload(nome="nota.xml", tamanho=500, content_type="text/xml")
        assert a.content_type == "text/xml"

    def test_extensao_invalida_levanta(self):
        with pytest.raises(ValidationError, match="não suportada"):
            ArquivoUpload(nome="arquivo.docx", tamanho=100, content_type="x")

    def test_tamanho_zero_levanta(self):
        with pytest.raises(ValidationError, match="vazio"):
            ArquivoUpload(nome="x.pdf", tamanho=0, content_type="application/pdf")

    def test_tamanho_excedido_levanta(self):
        with pytest.raises(ValidationError, match="excede"):
            ArquivoUpload(nome="x.pdf", tamanho=TAMANHO_MAX + 1, content_type="x")


class TestValidarArquivos:
    def _make_upload(self, name, size=100):
        # Cria UploadFile mock-like
        up = UploadFile(filename=name, file=io.BytesIO(b"x" * size))
        return up

    def test_lista_vazia_retorna_erro(self):
        erros = validar_arquivos([])
        assert len(erros) == 1
        assert "Nenhum" in erros[0]

    def test_extensao_nao_aceita_aponta_erro(self):
        erros = validar_arquivos([self._make_upload("evil.exe")])
        assert any("extensão" in e for e in erros)

    def test_pdf_e_xml_aceitos_sem_erro(self):
        erros = validar_arquivos([
            self._make_upload("a.pdf"),
            self._make_upload("b.xml"),
        ])
        assert erros == []

    def test_acima_de_100_arquivos_bloqueado(self):
        ups = [self._make_upload(f"f{i}.pdf") for i in range(101)]
        erros = validar_arquivos(ups)
        assert len(erros) == 1
        assert "100" in erros[0]


class TestUploadAuditoriaParams:
    def test_defaults(self):
        p = UploadAuditoriaParams()
        assert p.modo_relatorio == "simples"
        assert p.formato_relatorio == "html"

    def test_valor_invalido_levanta(self):
        with pytest.raises(ValidationError):
            UploadAuditoriaParams(modo_relatorio="x")  # type: ignore[arg-type]

    def test_extensoes_aceitas_completas(self):
        assert ".pdf" in EXTENSOES_ACEITAS
        assert ".xml" in EXTENSOES_ACEITAS


# ── Usuários ─────────────────────────────────────────────────────────────────

class TestLoginRequest:
    def test_email_valido_senha_min(self):
        lr = LoginRequest(email="a@b.com", password="123456")
        assert lr.email == "a@b.com"

    def test_email_invalido_levanta(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="invalido", password="123456")

    def test_senha_curta_levanta(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com", password="123")


class TestSenhaUpdate:
    def test_senha_forte(self):
        s = SenhaUpdate(senha_atual="oldpass1", nova_senha="Forte123!")
        assert s.nova_senha == "Forte123!"

    def test_sem_maiuscula(self):
        with pytest.raises(ValidationError, match="maiúscula"):
            SenhaUpdate(senha_atual="oldpass1", nova_senha="fraca123!")

    def test_sem_minuscula(self):
        with pytest.raises(ValidationError, match="minúscula"):
            SenhaUpdate(senha_atual="oldpass1", nova_senha="FORTE123!")

    def test_sem_numero(self):
        with pytest.raises(ValidationError, match="número"):
            SenhaUpdate(senha_atual="oldpass1", nova_senha="ForteSemNum!")

    def test_sem_especial(self):
        with pytest.raises(ValidationError, match="especial"):
            SenhaUpdate(senha_atual="oldpass1", nova_senha="ForteNum123")


class TestOutrosSchemasUsuario:
    def test_usuario_response(self):
        u = UsuarioResponse(id=1, nome="X", email="a@b.com", role="admin", is_active=True)
        assert u.is_active

    def test_token_response(self):
        u = UsuarioResponse(id=1, nome="X", email="a@b.com", role="user", is_active=True)
        t = TokenResponse(access_token="jwt.token.here", user=u)
        assert t.token_type == "bearer"

    def test_me_response(self):
        m = MeResponse(id=1, email="a@b.com", nome="X", role="admin")
        assert m.role == "admin"
