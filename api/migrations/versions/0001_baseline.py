"""Baseline: drafts and approvals as of slice 4.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("invoice_id", sa.String(64), nullable=False, index=True),
        sa.Column("invoice_number", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("days_overdue", sa.Integer, nullable=False),
        sa.Column("priority", sa.Numeric(16, 2), nullable=False),
        sa.Column("tone", sa.String(32)),
        sa.Column("subject", sa.Text),
        sa.Column("body", sa.Text),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("hold_reason", sa.String(32)),
        sa.Column("violations", sa.JSON, nullable=False),
        sa.Column("tries", sa.Integer, nullable=False),
        sa.Column("model", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index("uq_draft_invoice_balance", "drafts", ["invoice_id", "balance"], unique=True)
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("draft_id", sa.Integer, sa.ForeignKey("drafts.id"), nullable=False, unique=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_index("uq_draft_invoice_balance", table_name="drafts")
    op.drop_table("drafts")
