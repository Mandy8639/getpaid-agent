"""Reset the end-to-end test database. Only a local database named like getpaid_*_e2e."""

import re

from sqlalchemy import text
from sqlalchemy.engine import make_url

from getpaid.config import get_settings
from getpaid.db import make_engine, migrate


def main() -> None:
    url = make_url(get_settings().database_url)
    name = url.database or ""
    if not re.fullmatch(r"[a-z0-9_]+_e2e", name) or url.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit(f"refusing to reset non-e2e or non-local database {name!r}")
    admin = make_engine(
        url.set(database="getpaid").render_as_string(hide_password=False), autocommit=True
    )
    with admin.connect() as c:
        if not c.execute(
            text("select 1 from pg_database where datname = :d"), {"d": url.database}
        ).first():
            c.execute(text(f'create database "{url.database}"'))
    admin.dispose()
    engine = make_engine(url.render_as_string(hide_password=False))
    with engine.begin() as c:
        c.execute(text("drop schema public cascade; create schema public"))
    engine.dispose()
    migrate(url.render_as_string(hide_password=False))


if __name__ == "__main__":
    main()
