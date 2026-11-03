"""Integration tests run against a real Postgres (docker compose up -d db), in a
separate vaani_test database that is recreated from the migrations each run."""

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PG = os.environ.get("TEST_PG", "localhost:5435")
TEST_DB = "vaani_test"
os.environ["DATABASE_URL"] = f"postgresql+psycopg://vaani_app:vaani_app@{PG}/{TEST_DB}"
os.environ["ADMIN_DATABASE_URL"] = f"postgresql+psycopg://vaani_admin:vaani_admin@{PG}/{TEST_DB}"
os.environ["AGENT_API_KEY"] = "test-key"
os.environ["WHATSAPP_APP_SECRET"] = "test-secret"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "test-verify"
os.environ["GEMINI_API_KEY"] = ""  # never call Google from tests; they use fakes

from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

import app.api.accounts as accounts_api  # noqa: E402
from app import clock  # noqa: E402
from app.db import app_engine, system_engine, system_session  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import DEMO_PASSWORDS, add_demo_logins, seed_demo  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
# Monday 2 Nov 2026, 9:00 AM in Hyderabad. The demo clinic opens at 10.
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=IST)
TUESDAY = "2026-11-03"


def admin_dsn(database: str) -> str:
    return f"postgresql://vaani_admin:vaani_admin@{PG}/{database}"


@pytest.fixture(scope="session")
def database():
    with psycopg.connect(admin_dsn("postgres"), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
        conn.execute(
            """DO $$ BEGIN
                 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vaani_app') THEN
                   CREATE ROLE vaani_app LOGIN PASSWORD 'vaani_app';
                 END IF;
               END $$"""
        )
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option("sqlalchemy.url", os.environ["ADMIN_DATABASE_URL"])
    command.upgrade(config, "head")
    yield


@pytest.fixture(scope="session", autouse=True)
async def dispose_engines():
    yield
    await app_engine().dispose()
    await system_engine().dispose()


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)


@pytest.fixture
def clean_db(database):
    with psycopg.connect(admin_dsn(TEST_DB), autocommit=True) as conn:
        conn.execute("TRUNCATE businesses CASCADE")


@pytest.fixture
async def clinic(clean_db):
    """The seeded demo clinic's business id."""
    async with system_session() as session:
        return await seed_demo(session)


@pytest.fixture
async def client(clinic):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer test-key", "X-Business-Id": str(clinic)},
    ) as c:
        yield c


# Dashboard logins ---------------------------------------------------------------

OWNER = "owner@sri-dental.example.com"
STAFF = "staff@sri-dental.example.com"


@pytest.fixture(autouse=True)
def fresh_login_limits(monkeypatch):
    monkeypatch.setattr(accounts_api, "login_limiter", accounts_api.RateLimiter())


@pytest.fixture
async def logins(clinic):
    async with system_session() as s:
        await add_demo_logins(s, clinic, "sri-dental")


def browser() -> httpx.AsyncClient:
    """A client with its own cookie jar, like a separate browser."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@asynccontextmanager
async def signed_in(email: str, password: str):
    async with browser() as c:
        r = await c.post("/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
async def owner(logins):
    async with signed_in(OWNER, DEMO_PASSWORDS["owner"]) as c:
        yield c


@pytest.fixture
async def staff(logins):
    async with signed_in(STAFF, DEMO_PASSWORDS["staff"]) as c:
        yield c
