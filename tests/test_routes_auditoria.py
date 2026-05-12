"""Testes da rota /auditoria — uploads, pipeline NFA-e, validação CPF/CNPJ."""
import io
import os
from unittest.mock import patch

os.environ["JWT_SECRET_KEY"] = "a" * 64

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _payload_minimo(cpf: str = "529.982.247-25"):
    return {
        "contribuinte_cpf": cpf,
        "contribuinte_nome": "Joao Lavrador",
        "is_pj": False,
        "is_segurado_especial": False,
        "notas": [{
            "numero": "001",
            "data": "2025-01-01",
            "natureza": "VENDA",
            "valor_total": 1000.0,
        }],
    }


# ── Upload PDF (legado) ──────────────────────────────────────────────────────

class TestUploadLegado:
    def test_upload_inicia_task_e_retorna_id(self):
        files = [("files", ("nota.pdf", io.BytesIO(b"%PDF"), "application/pdf"))]
        res = client.post("/auditoria/upload/1", files=files)
        assert res.status_code == 200
        assert "task_id" in res.json()

    def test_status_task_inexistente_404(self):
        res = client.get("/auditoria/status/nao-existe")
        assert res.status_code == 404

    def test_status_task_existente_retorna_payload(self):
        files = [("files", ("nota.pdf", io.BytesIO(b"%PDF"), "application/pdf"))]
        criado = client.post("/auditoria/upload/1", files=files)
        task_id = criado.json()["task_id"]
        res = client.get(f"/auditoria/status/{task_id}")
        assert res.status_code == 200
        assert "status" in res.json()


# ── Validação CPF/CNPJ no AuditoriaCompletaRequest ───────────────────────────

class TestValidacaoDocumento:
    def test_cnpj_valido_aceito(self):
        payload = _payload_minimo("11.222.333/0001-81")
        with patch("api.routes.auditoria.processar_nfae",
                   return_value={"score": 10, "agentes": {}}):
            res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 200

    def test_cpf_invalido_dv_retorna_422(self):
        payload = _payload_minimo("123.456.789-00")
        res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 422

    def test_cnpj_invalido_dv_retorna_422(self):
        payload = _payload_minimo("11.222.333/0001-99")
        res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 422

    def test_documento_tamanho_invalido_422(self):
        payload = _payload_minimo("123456")
        res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 422


# ── Pipeline /auditoria/nfae ─────────────────────────────────────────────────

class TestPipelineNfae:
    def test_sucesso_armazena_resultado_e_retorna_id(self):
        payload = _payload_minimo()
        fake_result = {"score": 25, "agentes": {"S1": "ok"}}
        with patch("api.routes.auditoria.processar_nfae",
                   return_value=fake_result):
            res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 200
        body = res.json()
        assert "result_id" in body
        assert body["score"] == 25

    def test_value_error_no_pipeline_retorna_422(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   side_effect=ValueError("notas inválidas")):
            res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 422
        assert "notas inválidas" in res.json()["detail"]

    def test_timeout_retorna_504(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   side_effect=TimeoutError("demorou demais")):
            res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 504

    def test_excecao_generica_retorna_500(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   side_effect=RuntimeError("falha qualquer")):
            res = client.post("/auditoria/nfae", json=payload)
        assert res.status_code == 500


# ── Resultado e PDF ──────────────────────────────────────────────────────────

class TestResultadoEPdf:
    def test_obter_resultado_inexistente_404(self):
        res = client.get("/auditoria/resultado/nao-existe-uuid")
        assert res.status_code == 404

    def test_obter_resultado_existente_retorna_dado(self):
        # Primeiro cria um resultado via pipeline
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   return_value={"score": 33}):
            criado = client.post("/auditoria/nfae", json=payload)
        rid = criado.json()["result_id"]
        res = client.get(f"/auditoria/resultado/{rid}")
        assert res.status_code == 200
        assert res.json()["score"] == 33

    def test_pdf_resultado_inexistente_404(self):
        res = client.get("/auditoria/relatorio/inexistente/pdf")
        assert res.status_code == 404

    def test_pdf_sucesso_retorna_application_pdf(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   return_value={"score": 1}):
            criado = client.post("/auditoria/nfae", json=payload)
        rid = criado.json()["result_id"]
        with patch("api.routes.auditoria.gerar_pdf_nfae",
                   return_value=b"%PDF-FAKE"):
            res = client.get(f"/auditoria/relatorio/{rid}/pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content == b"%PDF-FAKE"


# ── /auditoria/nfae/relatorio (pipeline + PDF inline) ────────────────────────

class TestNfaeRelatorio:
    def test_sucesso_retorna_pdf(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae", return_value={"x": 1}), \
             patch("api.routes.auditoria.gerar_pdf_nfae", return_value=b"%PDF-OK"):
            res = client.post("/auditoria/nfae/relatorio", json=payload)
        assert res.status_code == 200
        assert res.content == b"%PDF-OK"

    def test_value_error_422(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   side_effect=ValueError("erro x")):
            res = client.post("/auditoria/nfae/relatorio", json=payload)
        assert res.status_code == 422

    def test_excecao_generica_500(self):
        payload = _payload_minimo()
        with patch("api.routes.auditoria.processar_nfae",
                   side_effect=RuntimeError("boom")):
            res = client.post("/auditoria/nfae/relatorio", json=payload)
        assert res.status_code == 500
