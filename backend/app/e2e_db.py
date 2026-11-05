"""A fresh database for the browser tests in web/e2e: the demo clinic, its logins
and a week of sample activity, rebuilt on every run so each run starts the same.

    E2E_PG=localhost:5435 python -m app.e2e_db

Playwright starts it (see web/playwright.config.ts) and then runs the API against
it, so the tests never touch your development data.
"""

import asyncio
import os
from pathlib import Path

PG = os.environ.get("E2E_PG", "localhost:5435")
NAME = "vaani_e2e"
ADMIN_URL = f"postgresql+psycopg://vaani_admin:vaani_admin@{PG}/{NAME}"
APP_URL = f"postgresql+psycopg://vaani_app:vaani_app@{PG}/{NAME}"


def recreate() -> None:
    import psycopg
    from alembic import command
    from alembic.config import Config

    with psycopg.connect(
        f"postgresql://vaani_admin:vaani_admin@{PG}/postgres", autocommit=True
    ) as c:
        c.execute(f"DROP DATABASE IF EXISTS {NAME} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {NAME}")
        c.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaani_app') THEN "
            "CREATE ROLE vaani_app LOGIN PASSWORD 'vaani_app'; END IF; END $$"
        )
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    config.set_main_option("sqlalchemy.url", ADMIN_URL)
    command.upgrade(config, "head")


async def seed() -> None:
    from app.db import system_session
    from app.seed import add_demo_activity, add_demo_logins, seed_demo

    async with system_session() as session:
        business_id = await seed_demo(session, slug="sri-dental")
        await add_demo_logins(session, business_id, "sri-dental")
        await add_demo_activity(session, business_id)


def main() -> None:
    # Before any app module reads its settings.
    os.environ["ADMIN_DATABASE_URL"] = ADMIN_URL
    os.environ["DATABASE_URL"] = APP_URL
    recreate()
    asyncio.run(seed())
    print(f"{NAME} ready: the demo clinic with its demo logins and sample activity")


if __name__ == "__main__":
    main()
