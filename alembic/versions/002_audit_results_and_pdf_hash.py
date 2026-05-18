"""Persistência de resultados NFA-e + hash SHA-256 do PDF emitido.

Revision ID: 002_audit_results_and_pdf_hash
Revises: 001_initial
Create Date: 2026-05-12

P0-2: tabela auditoria_resultados substitui o dict in-memory resultados_store.
P0-6: coluna laudos.pdf_sha256 garante integridade jurídica do laudo emitido.
Inclui também:
- audit_tasks (modelo adicionado depois do initial; criada via create_all em
  dev, mas explícita aqui para Postgres em produção).
- Índices em laudos.cliente_id (FK sem index gerava full scan em JOIN).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "002_audit_results_and_pdf_hash"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tabela audit_tasks (idempotente — pode já existir via create_all)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tabelas = inspector.get_table_names()

    if "audit_tasks" not in tabelas:
        op.create_table(
            "audit_tasks",
            sa.Column("task_id", sa.String(128), primary_key=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="iniciado"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("payload_json", sa.Text()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # P0-2: tabela auditoria_resultados
    if "auditoria_resultados" not in tabelas:
        op.create_table(
            "auditoria_resultados",
            sa.Column("result_id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), index=True),
            sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), index=True),
            sa.Column("audit_hash", sa.String(64), index=True),
            sa.Column("pdf_sha256", sa.String(64)),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )

    # P0-6: laudos.pdf_sha256
    colunas_laudos = {c["name"] for c in inspector.get_columns("laudos")}
    if "pdf_sha256" not in colunas_laudos:
        op.add_column("laudos", sa.Column("pdf_sha256", sa.String(64)))

    # Índice em laudos.cliente_id (FK sem index)
    indices_laudos = {idx["name"] for idx in inspector.get_indexes("laudos")}
    if "ix_laudos_cliente_id" not in indices_laudos:
        op.create_index("ix_laudos_cliente_id", "laudos", ["cliente_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indices_laudos = {idx["name"] for idx in inspector.get_indexes("laudos")}
    if "ix_laudos_cliente_id" in indices_laudos:
        op.drop_index("ix_laudos_cliente_id", table_name="laudos")

    colunas_laudos = {c["name"] for c in inspector.get_columns("laudos")}
    if "pdf_sha256" in colunas_laudos:
        op.drop_column("laudos", "pdf_sha256")

    tabelas = inspector.get_table_names()
    if "auditoria_resultados" in tabelas:
        op.drop_table("auditoria_resultados")
    if "audit_tasks" in tabelas:
        op.drop_table("audit_tasks")
