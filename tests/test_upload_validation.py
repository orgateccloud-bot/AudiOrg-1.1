"""Testes para a validação de upload de PDF em POST /auditoria/upload/{client_id}.

Cobre o quick-win P0-1 do relatório de aprimoramento v8.0:
- Nome de arquivo inválido (path traversal) → 400
- Extensão diferente de .pdf → 415
- content-type não suportado → 415
- Arquivo vazio → 400
- Tamanho acima do limite → 413
- Magic-bytes inválido (não começa com %PDF-) → 415
- Lote acima do limite de arquivos → 413
- Lote ok (todos PDFs válidos pequenos) → aceita

Inclui token JWT em todas as requisições (auth obrigatória pós-fix P0).
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-key-32-bytes-long-suficient-for-tests")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_upload.db")

from api.main import app
from api.auth.security import create_token_pair
from api.routes import auditoria as auditoria_route
from nfa_extractor.infrastructure.database_v2 import Cliente, SessionLocal, init_db


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()
    with SessionLocal() as db:
        if db.query(Cliente).filter_by(cpf_cnpj="111.111.111-11").first() is None:
            db.add(Cliente(nome="Cliente Upload Teste", cpf_cnpj="111.111.111-11"))
            db.commit()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def cliente_id() -> int:
    with SessionLocal() as db:
        c = db.query(Cliente).filter_by(cpf_cnpj="111.111.111-11").first()
        return c.id


@pytest.fixture
def auth_headers() -> dict[str, str]:
    pair = create_token_pair({"sub": "1", "email": "admin@x.com", "role": "admin"})
    return {"Authorization": f"Bearer {pair.access_token}"}


@pytest.fixture(autouse=True)
def _limites_reduzidos(monkeypatch: pytest.MonkeyPatch):
    """Reduz os limites do módulo para exercer as bordas sem fabricar 10 MB."""
    monkeypatch.setattr(auditoria_route, "UPLOAD_MAX_BYTES", 1024)
    monkeypatch.setattr(auditoria_route, "UPLOAD_LOTE_MAX_BYTES", 2048)
    monkeypatch.setattr(auditoria_route, "UPLOAD_MAX_FILES", 3)


def _pdf_bytes(tamanho: int = 256, magic: bytes = b"%PDF-1.4\n") -> bytes:
    """Gera bytes que começam com magic-bytes de PDF e atingem o tamanho pedido."""
    corpo = magic + b"X" * max(0, tamanho - len(magic))
    return corpo[:tamanho] if tamanho > 0 else corpo


def test_nome_com_path_traversal_rejeitado(client: TestClient, cliente_id: int, auth_headers: dict):
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("../etc/passwd.pdf", _pdf_bytes(), "application/pdf"))],
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "inv" in resp.json()["detail"].lower()


def test_extensao_nao_pdf_rejeitada(client: TestClient, cliente_id: int, auth_headers: dict):
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("malicioso.exe", b"MZ\x90\x00", "application/octet-stream"))],
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_content_type_nao_pdf_rejeitado(client: TestClient, cliente_id: int, auth_headers: dict):
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("nota.pdf", _pdf_bytes(), "image/png"))],
        headers=auth_headers,
    )
    assert resp.status_code == 415


def test_arquivo_vazio_rejeitado(client: TestClient, cliente_id: int, auth_headers: dict):
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("vazio.pdf", b"", "application/pdf"))],
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_tamanho_acima_do_limite_rejeitado(client: TestClient, cliente_id: int, auth_headers: dict):
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("grande.pdf", _pdf_bytes(2048), "application/pdf"))],
        headers=auth_headers,
    )
    assert resp.status_code == 413


def test_magic_bytes_invalido_rejeitado(client: TestClient, cliente_id: int, auth_headers: dict):
    png_fake = b"\x89PNG\r\n\x1a\n" + b"X" * 100
    resp = client.post(
        f"/auditoria/upload/{cliente_id}",
        files=[("files", ("fake.pdf", png_fake, "application/pdf"))],
        headers=auth_headers,
    )
    assert resp.status_code == 415
    detalhe = resp.json()["detail"].lower()
    assert "magic" in detalhe or "pdf válido" in detalhe


def test_lote_acima_do_limite_de_arquivos_rejeitado(client: TestClient, cliente_id: int, auth_headers: dict):
    files = [
        ("files", (f"n{i}.pdf", _pdf_bytes(128), "application/pdf"))
        for i in range(4)
    ]
    resp = client.post(f"/auditoria/upload/{cliente_id}", files=files, headers=auth_headers)
    assert resp.status_code == 413


def test_lote_valido_aceito(client: TestClient, cliente_id: int, auth_headers: dict):
    files = [
        ("files", (f"nota_{i}.pdf", _pdf_bytes(256), "application/pdf"))
        for i in range(2)
    ]
    resp = client.post(f"/auditoria/upload/{cliente_id}", files=files, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body
