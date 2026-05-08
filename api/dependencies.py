"""
ORGATEC – Dependências FastAPI compartilhadas.

Centraliza dependências reutilizáveis entre routers para evitar duplicação.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from nfa_extractor.infrastructure.database_v2 import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Dependency que injeta uma session do SQLAlchemy e garante close ao final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
