"""The public booking page's API: no login, one business per URL, same booking rules.

Demo clinic: Mon-Sat 10:00-13:30 and 17:00-21:00, closed Sunday. "Now" is Mon 2 Nov, 9:00.
"""

from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

import app.api.public as public_api
from app.db import system_session
from app.main import app
from app.models import Booking
from tests.conftest import TUESDAY

SUNDAY = "2026-11-08"


@pytest.fixture(autouse=True)
def fresh_limits(monkeypatch):
    monkeypatch.setattr(public_api, "booking_limiter", public_api.RateLimiter())
    monkeypatch.setattr(public_api, "lookup_limiter", public_api.RateLimiter())


@pytest.fixture
async def visitor(clinic):
    """A browser with no login and no agent key."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def times(slots: list[dict]) -> list[str]:
    return [datetime.fromisoformat(s["start_at"]).strftime("%H:%M") for s in slots]


async def book(visitor, start=f"{TUESDAY}T18:00:00+05:30", **body):
    body = {
        "service": "RCT consultation",
        "start_at": start,
        "customer_name": "Ravi",
        "phone": "98765 43210",
        **body,
    }
    return await visitor.post("/v1/public/sri-dental/bookings", json=body)


async def test_page_shows_what_a_patient_needs_and_nothing_internal(visitor):
    r = await visitor.get("/v1/public/sri-dental")
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["name"] == "Sri Dental Clinic" and page["today"] == "2026-11-02"
    assert {"name": "RCT consultation", "duration_min": 30, "price_inr": 500} in page["services"]
    assert {h["weekday"] for h in page["hours"]} == {0, 1, 2, 3, 4, 5}  # closed Sunday
    assert not {"id", "greeting", "whatsapp_phone_number_id", "plan", "staff"} & page.keys()


async def test_unknown_business(visitor):
    assert (await visitor.get("/v1/public/nobody")).status_code == 404


async def test_a_day_lists_every_free_time(visitor):
    r = await visitor.get(
        "/v1/public/sri-dental/slots", params={"service": "RCT consultation", "date": TUESDAY}
    )
    assert r.status_code == 200, r.text
    slots = times(r.json()["slots"])
    assert slots[:3] == ["10:00", "10:15", "10:30"]
    assert "13:00" in slots and "13:15" not in slots  # a 30-minute RCT must end by 13:30
    assert "17:00" in slots and slots[-1] == "20:30"


async def test_a_closed_day_points_to_the_next_open_one(visitor):
    r = await visitor.get(
        "/v1/public/sri-dental/slots", params={"service": "RCT consultation", "date": SUNDAY}
    )
    assert r.json()["slots"] == [] and r.json()["next_free_date"] == "2026-11-09"


@pytest.mark.parametrize("day", ["2026-11-01", "2026-11-16"])  # yesterday; past 14 days
async def test_days_outside_the_booking_window_are_refused(visitor, day):
    r = await visitor.get(
        "/v1/public/sri-dental/slots", params={"service": "RCT consultation", "date": day}
    )
    assert r.status_code == 422


async def test_booking_online_takes_the_slot(visitor):
    r = await book(visitor)
    assert r.status_code == 201, r.text
    assert r.json()["staff"] == "Dr. Lakshmi Reddy" and r.json()["customer_name"] == "Ravi"

    async with system_session() as s:
        booking = await s.scalar(select(Booking))
    assert booking.source == "online" and booking.conversation_id is None

    after = await visitor.get(
        "/v1/public/sri-dental/slots", params={"service": "RCT consultation", "date": TUESDAY}
    )
    assert "18:00" not in times(after.json()["slots"])


async def test_a_taken_slot_is_refused_with_other_times(visitor):
    assert (await book(visitor)).status_code == 201
    r = await book(visitor, customer_name="Sita", phone="9123456780")
    assert r.status_code == 409
    assert r.json()["alternatives"]  # nearby free times to pick from


async def test_bad_phone_numbers_are_refused(visitor):
    assert (await book(visitor, phone="12345")).status_code == 422


async def test_bookings_are_limited_per_visitor(visitor):
    for hour in (10, 11, 12, 17, 18):
        assert (await book(visitor, start=f"{TUESDAY}T{hour}:00:00+05:30")).status_code == 201
    assert (await book(visitor, start=f"{TUESDAY}T19:00:00+05:30")).status_code == 429


async def test_online_bookings_are_not_counted_as_vaanis(visitor, owner):
    assert (await book(visitor)).status_code == 201
    overview = (await owner.get("/v1/dashboard/overview")).json()
    assert overview["agent_bookings_7d"] == 0
