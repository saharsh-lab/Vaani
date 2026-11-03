"""One business can never read or change another's data, and the database (not
just the API code) enforces it."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import app_engine, system_session, tenant_session
from app.models import Booking, Business, Customer, Service, Staff
from app.seed import seed_demo
from tests.conftest import NOW

PHONE = "9876543210"


@pytest.fixture
async def other_clinic(clinic):
    async with system_session() as session:
        return await seed_demo(session, slug="other-clinic", name="Other Clinic")


async def test_api_hides_other_tenants_bookings(client, other_clinic):
    booking = (
        await client.post(
            "/v1/tools/create_booking",
            json={
                "service": "RCT consultation",
                "start_at": "2026-11-03T18:00:00",
                "customer_name": "Ravi",
                "phone": PHONE,
            },
        )
    ).json()
    as_other = {"X-Business-Id": str(other_clinic)}

    found = await client.post("/v1/tools/find_booking", json={"phone": PHONE}, headers=as_other)
    assert found.json()["bookings"] == []

    cancel = {"booking_id": booking["booking_id"], "action": "cancel"}
    r = await client.post("/v1/tools/reschedule_or_cancel", json=cancel, headers=as_other)
    assert r.status_code == 404

    mine = await client.post("/v1/tools/find_booking", json={"phone": PHONE})
    assert mine.json()["bookings"][0]["status"] == "confirmed"


async def test_rls_limits_reads_to_own_rows(clinic, other_clinic):
    async with tenant_session(other_clinic) as s:
        assert await s.scalar(select(func.count()).select_from(Service)) == 5
        assert await s.get(Business, clinic) is None


async def test_rls_blocks_writing_rows_for_another_tenant(clinic, other_clinic):
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(other_clinic) as s:
            s.add(Customer(business_id=clinic, phone="+919999999999"))
            await s.flush()


async def test_no_tenant_means_no_rows(clinic):
    async with AsyncSession(app_engine()) as s:
        assert await s.scalar(select(func.count()).select_from(Service)) == 0


async def test_unknown_or_missing_credentials(client, clinic):
    r = await client.get("/v1/agent/context", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    r = await client.get(
        "/v1/agent/context", headers={"X-Business-Id": "00000000-0000-0000-0000-000000000000"}
    )
    assert r.status_code == 404


async def test_database_itself_rejects_double_booking(clinic):
    """Bypass the API entirely: the exclusion constraint alone stops an overlap."""
    async with system_session() as s:
        lakshmi = await s.scalar(select(Staff.id).where(Staff.name == "Dr. Lakshmi Reddy"))
        rct = await s.scalar(select(Service.id).where(Service.name == "RCT consultation"))
        customer = Customer(business_id=clinic, phone="+919876543210")
        s.add(customer)
        await s.flush()

    def booking(start_min: int, status: str = "confirmed") -> Booking:
        from datetime import timedelta

        start = NOW.replace(hour=18) + timedelta(minutes=start_min)
        return Booking(
            business_id=clinic,
            customer_id=customer.id,
            service_id=rct,
            staff_id=lakshmi,
            start_at=start,
            end_at=start + timedelta(minutes=30),
            status=status,
            source="dashboard",
        )

    async with system_session() as s:
        s.add(booking(0))
    async with system_session() as s:
        s.add(booking(30))  # back-to-back is fine: ranges are [start, end)
        s.add(booking(15, status="cancelled"))  # cancelled bookings don't block
    with pytest.raises(IntegrityError, match="bookings_no_overlap"):
        async with system_session() as s:
            s.add(booking(15))
