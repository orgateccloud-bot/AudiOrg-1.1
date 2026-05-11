"""tabela de resultados dos agentes S1-S7

Revision ID: 002_agent_results
Revises: 001_initial
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_agent_results"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("laudo_id", sa.Integer(), sa.ForeignKey("laudos.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("agent_id", sa.String(10), nullable=False),          # S1..S7
        sa.Column("status", sa.String(20), nullable=False),            # APROVADO|REJEITADO|ESCALADO|ERRO
        sa.Column("output", sa.Text(), nullable=True),                  # JSON serializado
        sa.Column("confidence", sa.Float(), server_default="0.0"),
        sa.Column("audit_hash", sa.String(64), nullable=True),
        sa.Column("modelo_usado", sa.String(50), nullable=True),        # haiku|sonnet|opus
        sa.Column("tokens_entrada", sa.Integer(), server_default="0"),
        sa.Column("tokens_saida", sa.Integer(), server_default="0"),
        sa.Column("latencia_ms", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "precalc_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("payload_hash", sa.String(16), unique=True, nullable=False, index=True),
        sa.Column("score_xgboost", sa.Float(), server_default="0.0"),
        sa.Column("score_lstm", sa.Float(), server_default="0.0"),
        sa.Column("tipologias_criticas", sa.Integer(), server_default="0"),
        sa.Column("detectores_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("laudo_id", sa.Integer(), sa.ForeignKey("laudos.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("tipo", sa.String(20), nullable=False),               # ESCALADO|APROVADO|REJEITADO|CONCLUIDO
        sa.Column("agent_id", sa.String(10), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("ts", sa.Float(), nullable=False),                    # unix timestamp
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("precalc_cache")
    op.drop_table("agent_results")
