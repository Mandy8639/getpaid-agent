"""Alembic: upgrading an empty database gives exactly the tables the code expects."""

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from getpaid.db import make_engine, metadata

ADMIN = "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid"
URL = ADMIN.rsplit("/", 1)[0] + "/getpaid_migrations_test"


def test_upgrade_head_matches_metadata_and_downgrades_cleanly() -> None:
    admin = make_engine(ADMIN, autocommit=True)
    with admin.connect() as c:
        c.execute(text("drop database if exists getpaid_migrations_test"))
        c.execute(text("create database getpaid_migrations_test"))
    admin.dispose()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", URL)
    command.upgrade(cfg, "head")
    engine = make_engine(URL)
    insp = inspect(engine)
    for table in metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        assert have == {c.name for c in table.columns}, table.name
    assert "uq_draft_invoice_balance" in {i["name"] for i in insp.get_indexes("drafts")}
    engine.dispose()
    command.downgrade(cfg, "base")
    engine = make_engine(URL)
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()


def test_migrate_stamps_a_pre_alembic_database_and_keeps_its_rows() -> None:
    from getpaid.db import migrate

    admin = make_engine(ADMIN, autocommit=True)
    with admin.connect() as c:
        c.execute(text("drop database if exists getpaid_migrations_test"))
        c.execute(text("create database getpaid_migrations_test"))
    admin.dispose()
    engine = make_engine(URL)
    with engine.begin() as c:  # simulate slice 1-4: tables made by create_all, no version table
        c.execute(
            text(
                "create table drafts (id serial primary key, invoice_id varchar(64) not null, "
                "invoice_number varchar(64) not null, customer_name varchar(255) not null, "
                "balance numeric(12,2) not null, days_overdue int not null, priority numeric(16,2) not null, "
                "tone varchar(32), subject text, body text, status varchar(16) not null, hold_reason varchar(32), "
                "violations json not null, tries int not null, model varchar(128), "
                "created_at timestamptz not null default now(), decided_at timestamptz)"
            )
        )
        c.execute(
            text("create unique index uq_draft_invoice_balance on drafts (invoice_id, balance)")
        )
        c.execute(
            text(
                "create table approvals (id serial primary key, draft_id int not null unique references drafts(id), "
                "decision varchar(16) not null, decided_at timestamptz not null default now())"
            )
        )
        c.execute(
            text(
                "insert into drafts (invoice_id, invoice_number, customer_name, balance, days_overdue, priority, "
                "status, violations, tries) values ('1','1','A',1,1,1,'pending','[]',0)"
            )
        )
    engine.dispose()
    migrate(URL)
    engine = make_engine(URL)
    with engine.connect() as c:
        assert c.execute(text("select count(*) from drafts")).scalar() == 1
        cols = {
            r[0]
            for r in c.execute(
                text(
                    "select column_name from information_schema.columns where table_name='approvals'"
                )
            )
        }
    assert {"final_subject", "final_body", "edited"} <= cols
    engine.dispose()


def test_migrated_schema_has_no_diff_against_the_code() -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    admin = make_engine(ADMIN, autocommit=True)
    with admin.connect() as c:
        c.execute(text("drop database if exists getpaid_migrations_test"))
        c.execute(text("create database getpaid_migrations_test"))
    admin.dispose()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", URL)
    command.upgrade(cfg, "head")
    engine = make_engine(URL)
    with engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(
                conn, opts={"compare_type": True, "compare_server_default": True}
            ),
            metadata,
        )
    engine.dispose()
    assert diff == [], diff
