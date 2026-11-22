"""Alembic environment: URL from getpaid settings unless the caller passes one."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from getpaid.config import get_settings
from getpaid.db import metadata

config = context.config
url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
config.set_main_option("sqlalchemy.url", url)
target_metadata = metadata


def run() -> None:
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
