from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings

# Tests pass their own URL; everything else uses the table-owner connection.
url = context.config.get_main_option("sqlalchemy.url") or get_settings().admin_database_url

if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported; run against a database.")

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=None)
    with context.begin_transaction():
        context.run_migrations()
