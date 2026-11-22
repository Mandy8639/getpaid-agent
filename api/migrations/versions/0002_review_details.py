"""Slice 5: case snapshot for history, final approved text, edited flag.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("case_snapshot", sa.JSON))
    op.add_column("approvals", sa.Column("final_subject", sa.Text))
    op.add_column("approvals", sa.Column("final_body", sa.Text))
    op.add_column(
        "approvals", sa.Column("edited", sa.Boolean, nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("approvals", "edited")
    op.drop_column("approvals", "final_body")
    op.drop_column("approvals", "final_subject")
    op.drop_column("drafts", "case_snapshot")
