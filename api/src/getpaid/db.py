"""Postgres tables (SQLAlchemy Core). Queries are built with Core expressions, never strings."""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    func,
)

metadata = MetaData()

drafts = Table(
    "drafts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("invoice_id", String(64), nullable=False, index=True),
    Column("invoice_number", String(64), nullable=False),
    Column("customer_name", String(255), nullable=False),
    Column("balance", Numeric(12, 2), nullable=False),
    Column("days_overdue", Integer, nullable=False),
    Column("priority", Numeric(16, 2), nullable=False),
    Column("tone", String(32)),
    Column("subject", Text),
    Column("body", Text),
    Column("status", String(16), nullable=False),  # pending | held | approved | skipped
    Column("hold_reason", String(32)),
    Column("violations", JSON, nullable=False, default=list),
    Column("tries", Integer, nullable=False, default=0),
    Column("model", String(128)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("decided_at", DateTime(timezone=True)),
)

# One draft per invoice state: re-running never re-drafts an invoice whose balance hasn't
# changed (whatever the owner decided), and concurrent runs can't create duplicates.
Index("uq_draft_invoice_balance", drafts.c.invoice_id, drafts.c.balance, unique=True)

approvals = Table(
    "approvals",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("draft_id", ForeignKey("drafts.id"), nullable=False, unique=True),
    Column("decision", String(16), nullable=False),  # approve | skip
    Column("decided_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


def make_engine(url: str, *, autocommit: bool = False) -> Engine:
    if autocommit:
        return create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    return create_engine(url, pool_pre_ping=True)
