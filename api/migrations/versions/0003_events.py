"""Slice 6: experiment events (one row per owner decision or rejected edit).

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("experiment_id", sa.String(32), nullable=False),
        sa.Column("arm", sa.String(16), nullable=False),
        sa.Column("draft_id", sa.Integer, sa.ForeignKey("drafts.id")),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("edited", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("seconds", sa.Float),
        sa.Column("simulated", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_events_experiment_arm", "events", ["experiment_id", "arm"])


def downgrade() -> None:
    op.drop_index("ix_events_experiment_arm", table_name="events")
    op.drop_table("events")
