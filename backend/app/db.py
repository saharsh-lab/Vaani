import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings


@lru_cache
def app_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def system_engine() -> AsyncEngine:
    return create_async_engine(get_settings().admin_database_url, pool_pre_ping=True)


@asynccontextmanager
async def tenant_session(business_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """A transaction that can only read and write one business's rows.

    It connects as vaani_app, which row-level security applies to, and sets
    app.business_id for this transaction only, so the setting can't leak to the
    next request that reuses the pooled connection.
    """
    async with AsyncSession(app_engine(), expire_on_commit=False) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.business_id', :bid, true)"),
                {"bid": str(business_id)},
            )
            yield session


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    """Bypasses row-level security. Use only for work that spans tenants:
    finding which business a slug or phone number belongs to, onboarding, seeding."""
    async with AsyncSession(system_engine(), expire_on_commit=False) as session:
        async with session.begin():
            yield session
