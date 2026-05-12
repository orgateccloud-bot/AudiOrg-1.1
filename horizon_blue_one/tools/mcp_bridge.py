"""MCP Bridge — Ferramentas MCP para agentes OrgAudi.

Expõe duas ferramentas compatíveis com Anthropic tool_use API:

  consultar_historico_produtor:
    Consulta SQLite (orgatec_sovereign.db) para buscar notas históricas
    de um produtor por CNPJ/CPF. Útil para S2 @Forense detectar padrões
    evolutivos que o lote atual não revela.

  buscar_dados_externos:
    HTTP GET com allowlist de domínios autorizados e timeout fixo.
    Permite S3 @Fiscal consultar situação cadastral em APIs externas
    (ex.: SEFAZ-GO, CADIN) sem abrir acesso irrestrito à internet.

Uso típico (em model_adapter.call_model_with_tools):
    resp, uso = await call_model_with_tools(
        prompt=...,
        system=...,
        tools=MCP_TOOLS,
        tool_handler=executar_tool,
        model_type=ModelType.SONNET,
    )
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger()

# ─── Allowlist de domínios externos permitidos ───────────────────────────────
# Fontes (uniadas):
#   1) mcp_allowlist.yaml (versionado, fonte canônica)
#   2) env MCP_FETCH_ALLOWLIST="dom1,dom2" (override em runtime)
#   3) hard-coded fallback (caso YAML ausente E env vazia)
_FALLBACK_HARDCODED = frozenset({
    "sefazgo.gov.br",
    "nfe.fazenda.gov.br",
    "receita.fazenda.gov.br",
    "cadin.fazenda.gov.br",
    "cidades.ibge.gov.br",
})


def _ler_yaml_allowlist() -> frozenset[str]:
    """Lê dominios do mcp_allowlist.yaml. Retorna frozenset vazio se ausente/erro."""
    yaml_path = Path(__file__).parent / "mcp_allowlist.yaml"
    if not yaml_path.exists():
        return frozenset()
    try:
        import yaml
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        dominios = data.get("dominios", [])
        return frozenset(str(d).strip().lower() for d in dominios if str(d).strip())
    except Exception as exc:
        logger.warning("mcp_allowlist_yaml_erro", error=str(exc))
        return frozenset()


def _carregar_allowlist() -> frozenset[str]:
    env = os.environ.get("MCP_FETCH_ALLOWLIST", "")
    dominios = {d.strip().lower() for d in env.split(",") if d.strip()}
    yaml_dominios = _ler_yaml_allowlist()
    if yaml_dominios:
        dominios |= yaml_dominios
    else:
        # YAML ausente → garante mínimo de segurança via hard-coded
        dominios |= _FALLBACK_HARDCODED
    return frozenset(dominios)


_FETCH_ALLOWLIST = _carregar_allowlist()
_FETCH_TIMEOUT   = 10.0  # segundos

# ─── Caminho do banco ─────────────────────────────────────────────────────────
def _db_path() -> Path:
    custom = os.environ.get("ORGAUDI_DB_PATH", "")
    if custom and Path(custom).exists():
        return Path(custom)
    raiz = Path(__file__).parent.parent.parent
    return raiz / "orgatec_sovereign.db"


# ─── Schemas de ferramentas (formato Anthropic tool_use) ─────────────────────

MCP_TOOLS: list[dict] = [
    {
        "name": "consultar_historico_produtor",
        "description": (
            "Consulta o banco OrgAudi para buscar notas fiscais históricas de um produtor "
            "identificado por CNPJ ou CPF. Use para detectar padrões temporais que o lote "
            "atual não revela (aceleração de volume, drift de preço, sazonalidade suspeita)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "documento": {
                    "type": "string",
                    "description": "CNPJ (14 dígitos) ou CPF (11 dígitos) do produtor.",
                },
                "limite": {
                    "type": "integer",
                    "description": "Número máximo de notas a retornar (padrão 50, máx 200).",
                    "default": 50,
                },
                "ano": {
                    "type": "integer",
                    "description": "Filtra por ano fiscal (ex: 2024). Opcional.",
                },
            },
            "required": ["documento"],
        },
    },
    {
        "name": "buscar_dados_externos",
        "description": (
            "Realiza GET HTTP em APIs externas autorizadas (SEFAZ, Receita Federal, CADIN). "
            "Retorna o corpo da resposta como texto. Use para cruzar dados da nota com "
            "situação cadastral em tempo real."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL completa do endpoint. Domínio deve estar na allowlist.",
                },
                "headers": {
                    "type": "object",
                    "description": "Headers HTTP adicionais (ex: Authorization). Opcional.",
                },
            },
            "required": ["url"],
        },
    },
]


# ─── Implementação das ferramentas ────────────────────────────────────────────

def _consultar_historico_produtor(documento: str, limite: int = 50, ano: int | None = None) -> dict:
    """Executa query read-only no SQLite e retorna notas históricas."""
    doc = "".join(c for c in documento if c.isdigit())
    limite = min(int(limite), 200)

    db = _db_path()
    if not db.exists():
        return {"erro": f"Banco não encontrado: {db}", "notas": []}

    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Detecta automaticamente tabelas disponíveis
        tabelas = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        tabela = None
        for candidato in ("notas_fiscais", "nfa", "auditoria_notas", "notas"):
            if candidato in tabelas:
                tabela = candidato
                break

        if not tabela:
            conn.close()
            return {"erro": "Nenhuma tabela de notas encontrada", "notas": [], "tabelas": list(tabelas)}

        colunas = {r[1] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}

        # Monta query adaptada às colunas disponíveis
        filtros = []
        params: list[Any] = []

        for col_doc in ("cnpj_remetente", "remetente_cnpj", "cpf_destinatario", "documento"):
            if col_doc in colunas:
                filtros.append(f"{col_doc} LIKE ?")
                params.append(f"%{doc}%")
                break

        if ano and "data_emissao" in colunas:
            filtros.append("strftime('%Y', data_emissao) = ?")
            params.append(str(ano))
        elif ano and "data" in colunas:
            filtros.append("strftime('%Y', data) = ?")
            params.append(str(ano))

        where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        order = "ORDER BY data_emissao DESC" if "data_emissao" in colunas else (
                "ORDER BY data DESC" if "data" in colunas else "")
        sql = f"SELECT * FROM {tabela} {where} {order} LIMIT ?"
        params.append(limite)

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        notas = [dict(r) for r in rows]
        logger.info("mcp_historico_consultado", documento=doc[:8], total=len(notas), tabela=tabela)
        return {"notas": notas, "total": len(notas), "tabela": tabela}

    except sqlite3.Error as exc:
        logger.warning("mcp_sqlite_erro", error=str(exc))
        return {"erro": str(exc), "notas": []}


def _buscar_dados_externos(url: str, headers: dict | None = None) -> dict:
    """GET HTTP com validação de allowlist e timeout fixo."""
    try:
        dominio = urlparse(url).hostname or ""
    except Exception:
        return {"erro": "URL inválida", "status": 400}

    # Verifica allowlist (domínio ou subdomínio)
    autorizado = any(
        dominio == d or dominio.endswith(f".{d}")
        for d in _FETCH_ALLOWLIST
    )
    if not autorizado:
        logger.warning("mcp_fetch_bloqueado", dominio=dominio)
        return {
            "erro": f"Domínio '{dominio}' não autorizado. Adicione em MCP_FETCH_ALLOWLIST.",
            "status": 403,
        }

    try:
        resp = httpx.get(url, headers=headers or {}, timeout=_FETCH_TIMEOUT, follow_redirects=True)
        logger.info("mcp_fetch_ok", dominio=dominio, status=resp.status_code, bytes=len(resp.content))
        return {
            "status": resp.status_code,
            "body":   resp.text[:8000],  # limita para não explodir contexto
            "headers": dict(resp.headers),
        }
    except httpx.TimeoutException:
        return {"erro": "Timeout após 10s", "status": 408}
    except httpx.RequestError as exc:
        return {"erro": str(exc), "status": 503}


# ─── Dispatcher (chamado pelo model_adapter) ──────────────────────────────────

async def executar_tool(tool_name: str, tool_input: dict) -> str:
    """Executa a ferramenta MCP e retorna resultado como JSON string."""
    if tool_name == "consultar_historico_produtor":
        resultado = _consultar_historico_produtor(
            documento=tool_input.get("documento", ""),
            limite=tool_input.get("limite", 50),
            ano=tool_input.get("ano"),
        )
    elif tool_name == "buscar_dados_externos":
        resultado = _buscar_dados_externos(
            url=tool_input.get("url", ""),
            headers=tool_input.get("headers"),
        )
    else:
        resultado = {"erro": f"Ferramenta desconhecida: {tool_name}"}

    return json.dumps(resultado, ensure_ascii=False, default=str)
