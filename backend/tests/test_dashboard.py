"""Owner and staff dashboard API: accounts, roles, tenant isolation, and that what
owners change in settings is what the agent then uses."""

from contextlib import asynccontextmanager

import httpx
import pytest

import app.api.accounts as accounts_api
from app.db import system_session
from app.main import app
from app.seed import DEMO_PASSWORDS, add_demo_logins
from tests.conftest import TUESDAY

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


# Accounts --------------------------------------------------------------------------------


async def test_signup_creates_a_business_and_signs_in(clean_db):
    async with browser() as c:
        r = await c.post(
            "/v1/auth/signup",
            json={
                "business_name": "Glow Salon & Spa",
                "business_type": "salon",
                "languages": ["hi", "en"],
                "owner_name": "Kavya",
                "email": "Kavya@Example.com",
                "password": "correct horse battery",
            },
        )
        assert r.status_code == 201, r.text
        me = r.json()
        assert me["user"]["role"] == "owner" and me["user"]["email"] == "kavya@example.com"
        assert me["business"]["slug"] == "glow-salon-spa"
        assert me["business"]["greeting"].startswith("Namaste! Glow Salon & Spa")
        assert "vaani_session" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]

        assert (await c.get("/v1/dashboard/me")).json()["business"]["name"] == "Glow Salon & Spa"
        hours = (await c.get("/v1/dashboard/hours")).json()
        assert len(hours) == 6 and hours[0]["open_time"] == "10:00:00"

        again = await c.post(
            "/v1/auth/signup",
            json={
                **{"business_name": "Other", "business_type": "salon", "owner_name": "X"},
                "email": "kavya@example.com",
                "password": "another password",
            },
        )
        assert again.status_code == 409


async def test_login_logout_and_bad_passwords(logins):
    async with browser() as c:
        r = await c.post("/v1/auth/login", json={"email": OWNER, "password": "nope-nope"})
        assert r.status_code == 401
        assert (await c.get("/v1/dashboard/me")).status_code == 401
        await c.post(
            "/v1/auth/login", json={"email": OWNER.upper(), "password": DEMO_PASSWORDS["owner"]}
        )
        assert (await c.get("/v1/dashboard/me")).json()["user"]["role"] == "owner"
        await c.post("/v1/auth/logout")
        assert (await c.get("/v1/dashboard/me")).status_code == 401


async def test_repeated_wrong_passwords_are_throttled(logins):
    async with browser() as c:
        codes = [
            (
                await c.post("/v1/auth/login", json={"email": OWNER, "password": "wrong-pass"})
            ).status_code
            for _ in range(11)
        ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


# Roles -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/dashboard/overview"),
        ("get", "/v1/dashboard/conversations"),
        ("get", "/v1/dashboard/team"),
        ("get", "/v1/dashboard/faqs"),
        ("put", "/v1/dashboard/hours"),
        ("post", "/v1/dashboard/services"),
        ("patch", "/v1/dashboard/business"),
    ],
)
async def test_staff_cannot_use_owner_pages(staff, method, path):
    body = [] if method == "put" else {}
    r = await staff.request(method, path, json=body)
    assert r.status_code == 403


async def test_staff_see_bookings_handoffs_services_and_doctors(staff):
    for path in ("bookings", "handoffs", "services", "staff"):
        assert (await staff.get(f"/v1/dashboard/{path}")).status_code == 200, path


async def test_other_businesses_are_invisible(owner, client, clinic):
    booking = (
        await client.post(
            "/v1/tools/create_booking",
            json={
                "service": "RCT consultation",
                "start_at": f"{TUESDAY}T18:00:00",
                "customer_name": "Ravi",
                "phone": "9876543210",
            },
        )
    ).json()
    async with browser() as other:
        await other.post(
            "/v1/auth/signup",
            json={
                "business_name": "Other Clinic",
                "business_type": "clinic",
                "owner_name": "O",
                "email": "o@other.example.com",
                "password": "password123",
            },
        )
        assert (await other.get(f"/v1/dashboard/bookings?start={TUESDAY}")).json() == []
        r = await other.post(
            f"/v1/dashboard/bookings/{booking['booking_id']}/status", json={"status": "cancelled"}
        )
        assert r.status_code == 404
    mine = (await owner.get(f"/v1/dashboard/bookings?start={TUESDAY}")).json()
    assert [b["status"] for b in mine] == ["confirmed"]


# Bookings and handoffs ------------------------------------------------------------------------


async def test_front_desk_books_marks_and_moves(staff):
    r = await staff.post(
        "/v1/dashboard/bookings",
        json={
            "service": "Teeth cleaning",
            "start_at": f"{TUESDAY}T10:30:00",
            "customer_name": "Walk-in Sita",
            "phone": "9123456789",
        },
    )
    assert r.status_code == 201, r.text
    booking_id = r.json()["id"]
    day = (await staff.get(f"/v1/dashboard/bookings?start={TUESDAY}")).json()
    assert day[0]["customer_name"] == "Walk-in Sita" and day[0]["source"] == "dashboard"

    moved = await staff.post(
        f"/v1/dashboard/bookings/{booking_id}/move", json={"start_at": f"{TUESDAY}T11:30:00"}
    )
    assert moved.json()["label"] == "Tue 3 Nov, 11:30 AM"
    assert (
        await staff.post(
            f"/v1/dashboard/bookings/{booking_id}/status", json={"status": "completed"}
        )
    ).status_code == 204
    week = (await staff.get(f"/v1/dashboard/bookings?start={TUESDAY}&days=7")).json()
    assert week[0]["status"] == "completed"

    taken = await staff.post(
        "/v1/dashboard/bookings",
        json={
            "service": "Teeth cleaning",
            "start_at": f"{TUESDAY}T22:00:00",
            "customer_name": "Late",
            "phone": "9000000000",
        },
    )
    assert taken.status_code == 409  # after hours: same checks as the agent


async def test_handoff_queue(owner, staff, client):
    conversation = (
        await client.post(
            "/v1/conversations", json={"channel": "voice", "customer_phone": "9876543210"}
        )
    ).json()
    await client.post(
        "/v1/tools/handoff_to_human",
        json={
            "reason": "wants the doctor",
            "summary": "Bleeding after extraction",
            "conversation_id": conversation["id"],
        },
    )
    (item,) = (await staff.get("/v1/dashboard/handoffs")).json()
    assert item["status"] == "open" and item["customer_phone"] == "+919876543210"

    assert (
        await staff.post(f"/v1/dashboard/handoffs/{conversation['id']}/claim")
    ).status_code == 204
    (item,) = (await owner.get("/v1/dashboard/handoffs")).json()
    assert item["status"] == "claimed" and item["assignee"] == "Anitha (front desk)"

    r = await staff.post(
        f"/v1/dashboard/handoffs/{conversation['id']}/resolve",
        json={"note": "Called back, advised to come in"},
    )
    assert r.status_code == 204
    assert (await staff.get("/v1/dashboard/handoffs")).json() == []
    (done,) = (await staff.get("/v1/dashboard/handoffs?status=resolved")).json()
    assert done["note"] == "Called back, advised to come in"
    assert (
        await staff.post(f"/v1/dashboard/handoffs/{conversation['id']}/claim")
    ).status_code == 409


# Owner pages ----------------------------------------------------------------------------------


async def test_conversation_list_and_transcript(owner, client):
    conversation = (
        await client.post(
            "/v1/conversations", json={"channel": "whatsapp", "customer_phone": "9876543210"}
        )
    ).json()
    turn = {
        "messages": [
            {"role": "user", "text": "Parking undaa?"},
            {
                "role": "tool",
                "tool_name": "search_knowledge",
                "tool_args": {"question": "parking"},
                "tool_result": {"results": []},
            },
            {"role": "assistant", "text": "Avunu, two-wheeler parking undi.", "latency_ms": 900},
        ],
        "outcome": "info",
        "cost_inr": 0.02,
        "language": "te-IN",
    }
    await client.post(f"/v1/conversations/{conversation['id']}/turns", json=turn)
    listing = (await owner.get("/v1/dashboard/conversations?channel=whatsapp")).json()
    assert listing["total"] == 1 and listing["items"][0]["messages"] == 3
    detail = (await owner.get(f"/v1/dashboard/conversations/{conversation['id']}")).json()
    assert [m["role"] for m in detail["transcript"]] == ["user", "tool", "assistant"]
    assert detail["language"] == "te-IN"


async def test_overview_counts_and_setup_checklist(owner, client):
    await client.post(
        "/v1/tools/create_booking",
        json={
            "service": "General consultation",
            "start_at": "2026-11-02T17:00:00",
            "customer_name": "Ravi",
            "phone": "9876543210",
        },
    )
    o = (await owner.get("/v1/dashboard/overview")).json()
    assert o["date"] == "2026-11-02" and o["bookings_today"] == 1
    assert o["next_bookings"][0]["customer_name"] == "Ravi"
    assert o["agent_bookings_7d"] == 1
    assert o["setup"] == {
        "services": True,
        "hours": True,
        "staff": True,
        "faqs": True,
        "greeting": True,
        "whatsapp": False,
    }


async def test_a_new_faq_is_what_the_agent_finds(owner, client):
    r = await owner.post(
        "/v1/dashboard/faqs",
        json={
            "title": "Wheelchair access",
            "content": "Q: Is the clinic wheelchair accessible? A: Yes, there is a ramp and a lift.",
        },
    )
    assert r.status_code == 201
    found = (
        await client.post("/v1/tools/search_knowledge", json={"question": "wheelchair access"})
    ).json()
    assert found["results"][0]["title"] == "Wheelchair access"

    await owner.put(
        f"/v1/dashboard/faqs/{r.json()['id']}",
        json={"title": "Wheelchair access", "content": "Q: Wheelchair? A: Ramp only, no lift."},
    )
    found = (
        await client.post("/v1/tools/search_knowledge", json={"question": "wheelchair"})
    ).json()
    assert "Ramp only" in found["results"][0]["content"]
    assert (await owner.delete(f"/v1/dashboard/faqs/{r.json()['id']}")).status_code == 204


async def test_holiday_and_hours_change_what_can_be_booked(owner, client):
    r = await owner.post(
        "/v1/dashboard/blocked",
        json={"start_date": TUESDAY, "end_date": TUESDAY, "reason": "Diwali"},
    )
    assert r.status_code == 201 and r.json()[0]["reason"] == "Diwali"
    slots = (
        await client.post(
            "/v1/tools/check_availability", json={"service": "RCT consultation", "date": TUESDAY}
        )
    ).json()
    assert slots["date"] == "2026-11-04"  # Tuesday is blocked

    overlapping = [
        {"weekday": 0, "open_time": "10:00", "close_time": "14:00"},
        {"weekday": 0, "open_time": "13:00", "close_time": "18:00"},
    ]
    assert (await owner.put("/v1/dashboard/hours", json=overlapping)).status_code == 422
    sunday_too = [{"weekday": d, "open_time": "09:00", "close_time": "12:00"} for d in range(7)]
    assert len((await owner.put("/v1/dashboard/hours", json=sunday_too)).json()) == 7
    slots = (
        await client.post(
            "/v1/tools/check_availability",
            json={"service": "General consultation", "date": "2026-11-08"},
        )
    ).json()
    assert slots["date"] == "2026-11-08"  # now open on Sunday


async def test_services_and_doctors(owner):
    created = await owner.post(
        "/v1/dashboard/services",
        json={"name": "Dental implant consultation", "duration_min": 30, "price_inr": 800},
    )
    assert created.status_code == 201
    assert (
        await owner.post(
            "/v1/dashboard/services",
            json={"name": "Dental implant consultation", "duration_min": 30},
        )
    ).status_code == 409
    doctor = await owner.post(
        "/v1/dashboard/staff", json={"name": "Dr. Kiran", "service_ids": [created.json()["id"]]}
    )
    assert (
        doctor.json()["service_ids"] == [created.json()["id"]]
        and doctor.json()["custom_hours"] is False
    )
    evenings = [{"weekday": 1, "open_time": "17:00", "close_time": "21:00"}]
    assert (
        len(
            (
                await owner.put(
                    f"/v1/dashboard/hours?staff_id={doctor.json()['id']}", json=evenings
                )
            ).json()
        )
        == 1
    )
    listed = {s["name"]: s for s in (await owner.get("/v1/dashboard/staff")).json()}
    assert listed["Dr. Kiran"]["custom_hours"] is True
    retired = await owner.patch(
        f"/v1/dashboard/services/{created.json()['id']}", json={"active": False}
    )
    assert retired.json()["active"] is False


async def test_team_members_and_deactivation(owner):
    r = await owner.post(
        "/v1/dashboard/team",
        json={
            "name": "Ramesh",
            "email": "ramesh@sri.example.com",
            "password": "temporary-pass",
            "role": "staff",
        },
    )
    assert r.status_code == 201
    async with signed_in("ramesh@sri.example.com", "temporary-pass") as ramesh:
        assert (await ramesh.get("/v1/dashboard/me")).json()["user"]["role"] == "staff"
        await owner.patch(f"/v1/dashboard/team/{r.json()['id']}", json={"active": False})
        assert (await ramesh.get("/v1/dashboard/me")).status_code == 401  # locked out at once
    me = (await owner.get("/v1/dashboard/me")).json()["user"]
    assert (
        await owner.patch(f"/v1/dashboard/team/{me['id']}", json={"active": False})
    ).status_code == 409
