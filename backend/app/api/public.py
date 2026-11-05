"""The business's public page: details, free times and online booking. No login.

Everything goes through the same booking engine as Vaani's tools, inside a
row-level-security session for the one business named in the URL, so the
double-booking constraint and opening hours apply exactly as on a call.
"""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.config import get_settings
from app.db import system_session, tenant_session
from app.errors import NotFound
from app.models import Business, Service, WorkingHours
from app.ratelimit import RateLimiter
from app.schemas import (
    BookingOut,
    CreateBookingIn,
    DaySlotsOut,
    PublicBookingIn,
    PublicBusinessOut,
    PublicHours,
    PublicService,
)
from app.services import bookings, scheduling

router = APIRouter(prefix="/v1/public", tags=["public"])

booking_limiter = RateLimiter()
lookup_limiter = RateLimiter()


def _client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so this is the visitor behind the host's proxy.
    return request.client.host if request.client else "unknown"


def _limit(limiter: RateLimiter, request: Request, per_hour: int, message: str) -> None:
    if not limiter.allow(_client_ip(request), per_hour):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message)


async def _business_session(slug: str) -> AsyncIterator[tuple[Business, AsyncSession]]:
    async with system_session() as s:
        found = await s.scalar(select(Business.id).where(Business.slug == slug))
    if found is None:
        raise NotFound(f"No business with slug {slug!r}.")
    async with tenant_session(found) as db:
        yield await db.get(Business, found), db


PublicSession = Annotated[tuple[Business, AsyncSession], Depends(_business_session)]


@router.get("/{slug}")
async def business_page(slug: str, request: Request, ctx: PublicSession) -> PublicBusinessOut:
    _limit(lookup_limiter, request, get_settings().public_lookups_per_ip_per_hour, "Slow down.")
    business, db = ctx
    services = await db.scalars(select(Service).where(Service.active).order_by(Service.name))
    hours = await db.scalars(
        select(WorkingHours)
        .where(WorkingHours.staff_id.is_(None))
        .order_by(WorkingHours.weekday, WorkingHours.open_time)
    )
    return PublicBusinessOut(
        slug=business.slug,
        name=business.name,
        type=business.type,
        address=business.address,
        phone=business.phone,
        languages=business.languages,
        timezone=business.timezone,
        today=clock.now().astimezone(ZoneInfo(business.timezone)).date(),
        book_days_ahead=get_settings().public_book_days_ahead,
        hours=[
            PublicHours(weekday=h.weekday, open_time=h.open_time, close_time=h.close_time)
            for h in hours
        ],
        services=[
            PublicService(
                name=s.name,
                duration_min=s.duration_min,
                price_inr=float(s.price_inr) if s.price_inr is not None else None,
            )
            for s in services
        ],
    )


@router.get("/{slug}/slots")
async def free_times(
    slug: str, service: str, date: dt.date, request: Request, ctx: PublicSession
) -> DaySlotsOut:
    _limit(lookup_limiter, request, get_settings().public_lookups_per_ip_per_hour, "Slow down.")
    business, db = ctx
    return await scheduling.day_slots(db, business, service, date)


@router.post("/{slug}/bookings", status_code=status.HTTP_201_CREATED)
async def book(
    slug: str, body: PublicBookingIn, request: Request, ctx: PublicSession
) -> BookingOut:
    _limit(
        booking_limiter,
        request,
        get_settings().public_bookings_per_ip_per_hour,
        "Too many bookings from this connection. Please call the clinic.",
    )
    business, db = ctx
    return await bookings.create_booking(
        db,
        business,
        CreateBookingIn(
            service=body.service,
            start_at=body.start_at,
            customer_name=body.customer_name,
            phone=body.phone,
            source="online",
        ),
    )
