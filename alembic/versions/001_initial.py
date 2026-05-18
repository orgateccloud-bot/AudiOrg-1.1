"""migração inicial — schema completo v8.0 (cross-DB: SQLite + Postgres)

Revision ID: 001_initial
Revises:
Create Date: 2026-04-28

Notas de compatibilidade:
- `sa.true()` / `sa.false()` substitui `sa.text("1")` para que `server_default`
  de Boolean funcione tanto em SQLite (renderiza `1`) quanto Postgres (`TRUE`).
- `sa.func.now()` é cross-DB.
- `audit_tasks` movida para migração 002_audit_results_and_pdf_hash (evita duplicação).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="user"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Clientes
    op.create_table(
        "clientes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("cpf_cnpj", sa.String(20), unique=True, nullable=False),
        sa.Column("data_cadastro", sa.DateTime(), server_default=sa.func.now()),
    )

    # Notas
    # UniqueConstraint inline porque SQLite não suporta ALTER TABLE ADD CONSTRAINT;
    # alembic.op.create_unique_constraint exigiria batch mode. Cross-DB fica mais
    # simples declarando dentro do create_table.
    op.create_table(
        "notas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chave_acesso", sa.String(44), unique=True, nullable=False, index=True),
        sa.Column("numero", sa.String(), index=True),
        sa.Column("emissao", sa.String()),
        sa.Column("natureza", sa.String()),
        sa.Column("laudo_ia", sa.Text()),
        sa.Column("data_auditoria", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("numero", "emissao", name="uq_nota_numero_emissao"),
    )

    # Produtos
    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nota_id", sa.Integer(), sa.ForeignKey("notas.id", ondelete="CASCADE")),
        sa.Column("codigo", sa.String()),
        sa.Column("descricao", sa.String()),
        sa.Column("quantidade", sa.Float()),
        sa.Column("vlr_total", sa.Float()),
    )

    # Laudos
    op.create_table(
        "laudos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("data_auditoria", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("veredito_ia", sa.Text()),
        sa.Column("qtd_notas", sa.Integer()),
        sa.Column("valor_total", sa.Float()),
        sa.Column("qtd_anomalias", sa.Integer()),
        sa.Column("pdf_path", sa.String(500)),
    )


def downgrade() -> None:
    op.drop_table("laudos")
    op.drop_table("produtos")
    op.drop_table("notas")
    op.drop_table("clientes")
    op.drop_table("users")
