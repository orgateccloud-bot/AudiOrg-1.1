"""ledger_entries — substitui o JSONL append-only por tabela queryable (#26)

Revision ID: 003_ledger_entries
Revises: 002_audit_results_and_pdf_hash
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_ledger_entries"
down_revision: Union[str, None] = "002_audit_results_and_pdf_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("requisicao_id", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(32), nullable=False),
        sa.Column("acao", sa.String(255), nullable=False),
        sa.Column("tier", sa.String(32)),
        sa.Column("status", sa.String(32), nullable=False, server_default="APROVADO"),
        sa.Column("audit_hash", sa.String(64)),
        sa.Column("payload_json", sa.Text()),
    )
    op.create_index("ix_ledger_entries_ts", "ledger_entries", ["ts"])
    op.create_index("ix_ledger_entries_requisicao_id", "ledger_entries", ["requisicao_id"])
    op.create_index("ix_ledger_entries_agent_id", "ledger_entries", ["agent_id"])
    op.create_index("ix_ledger_entries_audit_hash", "ledger_entries", ["audit_hash"])


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_audit_hash", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_agent_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_requisicao_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_ts", table_name="ledger_entries")
    op.drop_table("ledger_entries")
