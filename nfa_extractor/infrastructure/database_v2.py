"""
ORGATEC — Models SQLAlchemy + Conexão Resiliente.

v7.2: SQLAlchemy 2.0 DeclarativeBase, UTC-aware defaults, engine resiliente.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarativa SQLAlchemy 2.0."""
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    nome: Mapped[str]            = mapped_column(String(255), nullable=False)
    email: Mapped[str]           = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str]            = mapped_column(String(50), default="user")
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    nome: Mapped[str]            = mapped_column(String(255), nullable=False)
    cpf_cnpj: Mapped[str]       = mapped_column(String(20), unique=True, nullable=False)
    data_cadastro: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    laudos = relationship("Laudo", back_populates="cliente", cascade="all, delete-orphan")


class NotaModel(Base):
    __tablename__ = "notas"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    chave_acesso: Mapped[str]    = mapped_column(String(44), unique=True, index=True, nullable=False)
    numero: Mapped[str | None]   = mapped_column(String, index=True)
    emissao: Mapped[str | None]  = mapped_column(String)
    natureza: Mapped[str | None] = mapped_column(String)
    laudo_ia: Mapped[str | None] = mapped_column(Text)
    data_auditoria: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    produtos = relationship("ProdutoModel", back_populates="nota", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("numero", "emissao", name="uq_nota_numero_emissao"),)


class ProdutoModel(Base):
    __tablename__ = "produtos"

    id: Mapped[int]               = mapped_column(Integer, primary_key=True, index=True)
    nota_id: Mapped[int | None]   = mapped_column(Integer, ForeignKey("notas.id", ondelete="CASCADE"))
    codigo: Mapped[str | None]    = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(String)
    quantidade: Mapped[float | None] = mapped_column(Float)
    vlr_total: Mapped[float | None]  = mapped_column(Float)

    nota = relationship("NotaModel", back_populates="produtos")


class Laudo(Base):
    __tablename__ = "laudos"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[int]      = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    data_auditoria: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    veredito_ia: Mapped[str | None]  = mapped_column(Text)
    qtd_notas: Mapped[int | None]    = mapped_column(Integer)
    valor_total: Mapped[float | None] = mapped_column(Float)
    qtd_anomalias: Mapped[int | None] = mapped_column(Integer)
    pdf_path: Mapped[str | None]     = mapped_column(String(500))
    # P0-6: integridade jurídica do PDF emitido (SHA-256 do binário)
    pdf_sha256: Mapped[str | None]   = mapped_column(String(64))

    cliente = relationship("Cliente", back_populates="laudos")


class AuditoriaResultado(Base):
    """Resultado completo do pipeline NFA-e — substitui resultados_store in-memory.

    P0-2: persistir para sobreviver a restart e suportar multi-instância.
    Mantém JSON completo do output do pipeline; user_id é coluna para query
    eficiente de "meus laudos".
    """

    __tablename__ = "auditoria_resultados"

    result_id: Mapped[str]       = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None]  = mapped_column(String(64), index=True)
    cliente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clientes.id"), index=True)
    audit_hash: Mapped[str | None]  = mapped_column(String(64), index=True)
    pdf_sha256: Mapped[str | None]  = mapped_column(String(64))
    payload_json: Mapped[str]    = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class AuditTask(Base):
    """Tabela de status/resultado de tasks de auditoria em andamento ou concluídas."""

    __tablename__ = "audit_tasks"

    task_id: Mapped[str]         = mapped_column(String(128), primary_key=True)
    status: Mapped[str]          = mapped_column(String(32), nullable=False, default="iniciado")
    progress: Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Conexão resiliente ───────────────────────────────────────────────────────

def _carregar_database_url() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        return db_url

    env_path = Path(__file__).parent.parent.parent / "config.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return ""


def get_engine():
    db_url = _carregar_database_url()

    if db_url:
        try:
            if "postgresql" in db_url:
                eng = create_engine(db_url, connect_args={"connect_timeout": 5})
                with eng.connect():
                    pass
                logger.info("DB: PostgreSQL conectado.")
                return eng
        except Exception as exc:
            logger.warning(f"Postgres indisponível ({exc}). Usando SQLite.")

    sqlite_url = "sqlite:///./orgatec_sovereign.db"
    eng = create_engine(sqlite_url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    logger.info("DB: SQLite WAL conectado.")
    return eng


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_or_create_cliente(session, nome: str, cpf_cnpj: str) -> Cliente:
    cliente = session.query(Cliente).filter_by(cpf_cnpj=cpf_cnpj).first()
    if cliente:
        return cliente
    novo = Cliente(nome=nome, cpf_cnpj=cpf_cnpj)
    session.add(novo)
    session.flush()
    return novo


def salvar_notas_bd(notas, laudo_texto: str = None) -> tuple[int, int]:
    salvas, ignoradas = 0, 0
    with SessionLocal() as db:
        for nfa in notas:
            chv = nfa.chave_acesso or nfa.numero
            if not chv:
                continue
            if db.query(NotaModel).filter_by(chave_acesso=chv).first():
                ignoradas += 1
                continue
            try:
                nova = NotaModel(
                    chave_acesso=chv,
                    numero=nfa.numero,
                    emissao=nfa.emissao,
                    natureza=nfa.natureza,
                    laudo_ia=laudo_texto,
                )
                nova.produtos = [
                    ProdutoModel(
                        codigo=p.codigo,
                        descricao=p.descricao,
                        quantidade=p.quantidade,
                        vlr_total=p.vlr_total,
                    )
                    for p in nfa.produtos
                ]
                db.add(nova)
                db.commit()
                salvas += 1
            except Exception as exc:
                db.rollback()
                logger.error(f"Erro ao salvar nota {chv}: {exc}")
    return salvas, ignoradas
