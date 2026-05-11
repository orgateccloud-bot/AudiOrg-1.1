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
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import auditoria as auditoria_route


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


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


def test_nome_com_path_traversal_rejeitado(client: TestClient):
    resp = client.post(
        "/auditoria/upload/1",
        files=[("files", ("../etc/passwd.pdf", _pdf_bytes(), "application/pdf"))],
    )
    assert resp.status_code == 400
    assert "inv" in resp.json()["detail"].lower()


def test_extensao_nao_pdf_rejeitada(client: TestClient):
    resp = client.post(
        "/auditoria/upload/1",
        files=[("files", ("malicioso.exe", b"MZ\x90\x00", "application/octet-stream"))],
    )
    assert resp.status_code == 415


def test_content_type_nao_pdf_rejeitado(client: TestClient):
    resp = client.post(
        "/auditoria/upload/1",
        files=[("files", ("nota.pdf", _pdf_bytes(), "image/png"))],
    )
    assert resp.status_code == 415


def test_arquivo_vazio_rejeitado(client: TestClient):
    resp = client.post(
        "/auditoria/upload/1",
        files=[("files", ("vazio.pdf", b"", "application/pdf"))],
    )
    assert resp.status_code == 400


def test_tamanho_acima_do_limite_rejeitado(client: TestClient):
    resp = client.post(
        "/auditoria/upload/1",
        files=[("files", ("grande.pdf", _pdf_bytes(2048), "application/pdf"))],
    )
    assert resp.status_code == 413


def test_magic_bytes_invalido_rejeitado(client: TestClient):
    png_fake = b"\x89PNG\r\n\x1a\n" + b"X" * 100
    resp = client.post(
        "/auditoria/upload/1",
        files=[("files", ("fake.pdf", png_fake, "application/pdf"))],
    )
    assert resp.status_code == 415
    detalhe = resp.json()["detail"].lower()
    assert "magic" in detalhe or "pdf válido" in detalhe


def test_lote_acima_do_limite_de_arquivos_rejeitado(client: TestClient):
    files = [
        ("files", (f"n{i}.pdf", _pdf_bytes(128), "application/pdf"))
        for i in range(4)
    ]
    resp = client.post("/auditoria/upload/1", files=files)
    assert resp.status_code == 413


def test_lote_valido_aceito(client: TestClient):
    files = [
        ("files", (f"nota_{i}.pdf", _pdf_bytes(256), "application/pdf"))
        for i in range(2)
    ]
    resp = client.post("/auditoria/upload/1", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body
