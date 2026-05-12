"""Testes extras do MCP Bridge — caminhos felizes (SQLite real + httpx mock)."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from horizon_blue_one.tools.mcp_bridge import (
    _buscar_dados_externos,
    _carregar_allowlist,
    _consultar_historico_produtor,
    _db_path,
    executar_tool,
)

# ── _db_path ─────────────────────────────────────────────────────────────────

class TestDbPath:
    def test_usa_orgaudi_db_path_env_se_existir(self, tmp_path, monkeypatch):
        db = tmp_path / "x.db"
        db.touch()
        monkeypatch.setenv("ORGAUDI_DB_PATH", str(db))
        assert _db_path() == db

    def test_fallback_quando_env_aponta_inexistente(self, monkeypatch):
        monkeypatch.setenv("ORGAUDI_DB_PATH", "/nao/existe/x.db")
        path = _db_path()
        assert path.name == "orgatec_sovereign.db"


# ── _carregar_allowlist ──────────────────────────────────────────────────────

class TestCarregarAllowlist:
    def test_env_adiciona_dominios(self, monkeypatch):
        monkeypatch.setenv("MCP_FETCH_ALLOWLIST", "exemplo.gov.br, outro.com")
        allow = _carregar_allowlist()
        assert "exemplo.gov.br" in allow
        assert "outro.com" in allow
        # Defaults preservados
        assert "sefazgo.gov.br" in allow

    def test_env_vazio_so_defaults(self, monkeypatch):
        monkeypatch.setenv("MCP_FETCH_ALLOWLIST", "")
        allow = _carregar_allowlist()
        assert "sefazgo.gov.br" in allow


# ── _consultar_historico_produtor (com DB real em tmp) ───────────────────────

def _criar_db_tmp(tmp_path: Path, tabela: str, colunas: list[tuple[str, str]],
                  linhas: list[tuple]) -> Path:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    cols_sql = ", ".join(f"{n} {t}" for n, t in colunas)
    conn.execute(f"CREATE TABLE {tabela} ({cols_sql})")
    placeholders = ",".join("?" * len(colunas))
    conn.executemany(f"INSERT INTO {tabela} VALUES ({placeholders})", linhas)
    conn.commit()
    conn.close()
    return db


class TestConsultarHistoricoSucesso:
    def test_consulta_notas_fiscais_por_cnpj(self, tmp_path):
        db = _criar_db_tmp(
            tmp_path, "notas_fiscais",
            [("id", "INTEGER"), ("cnpj_remetente", "TEXT"),
             ("valor", "REAL"), ("data_emissao", "TEXT")],
            [(1, "12345678000100", 1000.0, "2025-01-15"),
             (2, "12345678000100", 500.0, "2024-06-20"),
             (3, "99999999000199", 200.0, "2025-03-01")],
        )
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=db):
            r = _consultar_historico_produtor("12345678000100")
        assert r["total"] == 2
        assert r["tabela"] == "notas_fiscais"

    def test_filtra_por_ano(self, tmp_path):
        db = _criar_db_tmp(
            tmp_path, "notas_fiscais",
            [("id", "INTEGER"), ("cnpj_remetente", "TEXT"),
             ("data_emissao", "TEXT")],
            [(1, "12345", "2025-01-01"), (2, "12345", "2024-06-01")],
        )
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=db):
            r = _consultar_historico_produtor("12345", ano=2025)
        assert r["total"] == 1

    def test_tabela_alternativa_nfa(self, tmp_path):
        db = _criar_db_tmp(
            tmp_path, "nfa",
            [("id", "INTEGER"), ("documento", "TEXT"), ("data", "TEXT")],
            [(1, "111", "2025-01-01")],
        )
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=db):
            r = _consultar_historico_produtor("111")
        assert r["tabela"] == "nfa"
        assert r["total"] == 1

    def test_sem_tabela_conhecida_erro(self, tmp_path):
        db = tmp_path / "vazio.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE outra (x INTEGER)")
        conn.commit()
        conn.close()
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=db):
            r = _consultar_historico_produtor("123")
        assert "erro" in r
        assert "tabelas" in r

    def test_sqlite_error_capturado(self, tmp_path, monkeypatch):
        db = tmp_path / "ok.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE notas_fiscais (id INTEGER)")
        conn.commit()
        conn.close()

        def boom(*a, **kw):
            raise sqlite3.Error("simulado")
        monkeypatch.setattr(sqlite3, "connect", boom)
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=db):
            r = _consultar_historico_produtor("123")
        assert "erro" in r
        assert "simulado" in r["erro"]


# ── _buscar_dados_externos (caminho feliz com httpx mockado) ─────────────────

class TestBuscarDadosExternosOk:
    def test_get_sucesso_em_dominio_autorizado(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.text = "<xml>ok</xml>"
        fake_resp.content = b"<xml>ok</xml>"
        fake_resp.headers = {"content-type": "text/xml"}

        with patch("horizon_blue_one.tools.mcp_bridge.httpx.get", return_value=fake_resp):
            r = _buscar_dados_externos("https://sefazgo.gov.br/api/status")
        assert r["status"] == 200
        assert r["body"] == "<xml>ok</xml>"

    def test_timeout_retorna_408(self):
        with patch("horizon_blue_one.tools.mcp_bridge.httpx.get",
                   side_effect=httpx.TimeoutException("tempo esgotado")):
            r = _buscar_dados_externos("https://sefazgo.gov.br/x")
        assert r["status"] == 408

    def test_request_error_retorna_503(self):
        with patch("horizon_blue_one.tools.mcp_bridge.httpx.get",
                   side_effect=httpx.RequestError("conexao falhou")):
            r = _buscar_dados_externos("https://sefazgo.gov.br/x")
        assert r["status"] == 503
        assert "conexao falhou" in r["erro"]

    def test_subdominio_de_autorizado_passa(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.text = "ok"
        fake_resp.content = b"ok"
        fake_resp.headers = {}
        with patch("horizon_blue_one.tools.mcp_bridge.httpx.get", return_value=fake_resp):
            r = _buscar_dados_externos("https://api.sefazgo.gov.br/path")
        assert r["status"] == 200

    def test_body_truncado_a_8000(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.text = "x" * 20_000
        fake_resp.content = fake_resp.text.encode()
        fake_resp.headers = {}
        with patch("horizon_blue_one.tools.mcp_bridge.httpx.get", return_value=fake_resp):
            r = _buscar_dados_externos("https://sefazgo.gov.br/big")
        assert len(r["body"]) == 8000


# ── executar_tool dispatch correto ───────────────────────────────────────────

class TestExecutarToolDispatch:
    @pytest.mark.asyncio
    async def test_consultar_historico_repassa_args(self, tmp_path):
        db = _criar_db_tmp(
            tmp_path, "notas",
            [("id", "INTEGER"), ("documento", "TEXT")],
            [(1, "111")],
        )
        with patch("horizon_blue_one.tools.mcp_bridge._db_path", return_value=db):
            resp = await executar_tool(
                "consultar_historico_produtor",
                {"documento": "111", "limite": 10},
            )
        dados = json.loads(resp)
        assert dados["total"] == 1
