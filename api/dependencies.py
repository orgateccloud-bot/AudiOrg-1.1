"""
ORGATEC – Dependências FastAPI compartilhadas.
Centraliza dependências reutilizáveis entre routers para evitar duplicação.

Dependências disponíveis:
- get_db()              → SQLAlchemy Session (Supabase via DATABASE_URL / SQLite em dev)
- get_supabase_client() → supabase-py Client (Auth, Storage, Realtime, RPC)
"""

from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session
from supabase import Client, create_client

from nfa_extractor.infrastructure.database_v2 import SessionLocal


# ─── SQLAlchemy (ORM / Alembic migrations) ──────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """Dependency que injeta uma session do SQLAlchemy e garante close ao final.

    Em produção conecta ao Supabase via DATABASE_URL (Transaction Pooler).
    Em desenvolvimento usa SQLite (orgatec_sovereign.db) como fallback.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Supabase Client (SDK supabase-py) ──────────────────────────────────────

@lru_cache(maxsize=1)
def _get_cached_supabase_client() -> Client:
    """Cria o cliente Supabase uma única vez (singleton por processo).

    Variáveis necessárias em config.env / ambiente:
        SUPABASE_URL          https://<project-ref>.supabase.co
        SUPABASE_ANON_KEY     chave anon pública (safe para frontend/server)
        SUPABASE_SERVICE_ROLE_KEY  chave privada (somente backend — não expor)

    Para operações de usuário autenticado use SUPABASE_ANON_KEY.
    Para operações administrativas (seed, migrations via RPC) use SUPABASE_SERVICE_ROLE_KEY.
    """
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL e SUPABASE_ANON_KEY (ou SUPABASE_SERVICE_ROLE_KEY) "
            "devem estar definidos em config.env. "
            "Consulte .env.example para obter as chaves no Supabase Dashboard."
        )

    return create_client(url, key)


def get_supabase_client() -> Client:
    """FastAPI Dependency que injeta o cliente Supabase.

    Uso em routers:

        from api.dependencies import get_supabase_client
        from supabase import Client

        @router.get("/exemplo")
        async def exemplo(supa: Client = Depends(get_supabase_client)):
            data = supa.table("clientes").select("*").execute()
            return data.data
    """
    return _get_cached_supabase_client()
