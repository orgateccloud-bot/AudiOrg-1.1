"""claude_stats — agregado de uso/custo Claude por (periodo, modelo) (#27)

Revision ID: 004_claude_stats
Revises: 003_ledger_entries
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_claude_stats"
down_revision: Union[str, None] = "003_ledger_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "claude_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("periodo", sa.String(32), nullable=False),
        sa.Column("modelo", sa.String(32), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd_acumulado", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "periodo", "modelo", name="uq_claude_stats_periodo_modelo",
        ),
    )
    op.create_index("ix_claude_stats_periodo", "claude_stats", ["periodo"])
    op.create_index("ix_claude_stats_modelo", "claude_stats", ["modelo"])


def downgrade() -> None:
    op.drop_index("ix_claude_stats_modelo", table_name="claude_stats")
    op.drop_index("ix_claude_stats_periodo", table_name="claude_stats")
    op.drop_table("claude_stats")
