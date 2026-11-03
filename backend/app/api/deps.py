"""Request dependencies: service authentication and the per-tenant DB session.

Agent workers (voice, WhatsApp, CLI) call the API with a shared secret plus the
business they're serving. Owner logins (Supabase JWT) arrive with the dashboard.
"""

import secrets
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import tenant_session
from app.errors import NotFound
from app.models import Business


async def require_agent_key(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = f"Bearer {get_settings().agent_api_key}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid agent key")


async def business_id(x_business_id: Annotated[uuid.UUID, Header()]) -> uuid.UUID:
    return x_business_id


async def tenant_db(
    bid: Annotated[uuid.UUID, Depends(business_id)],
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(bid) as session:
        yield session


TenantDB = Annotated[AsyncSession, Depends(tenant_db)]


async def current_business(
    db: TenantDB, bid: Annotated[uuid.UUID, Depends(business_id)]
) -> Business:
    business = await db.get(Business, bid)  # row-level security hides other tenants
    if business is None:
        raise NotFound("Unknown business.")
    return business


CurrentBusiness = Annotated[Business, Depends(current_business)]
