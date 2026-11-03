"""The six agent tools, through the HTTP API, against the seeded demo clinic.

Demo clinic: Mon-Sat 10:00-13:30 and 17:00-21:00, closed Sunday. Dr. Lakshmi does
everything; Dr. Arjun works evenings and doesn't do RCT. "Now" is Mon 2 Nov, 9:00.
"""

import asyncio
from datetime import datetime

from sqlalchemy import select

from app import clock
from app.db import system_session
from app.models import BlockedSlot, Conversation
from tests.conftest import IST, TUESDAY

PHONE = "9876543210"


def times(slots: list[dict]) -> list[str]:
    return [datetime.fromisoformat(s["start_at"]).strftime("%H:%M") for s in slots]


async def availability(client, **body):
    body = {"service": "RCT consultation", "date": TUESDAY, **body}
    return await client.post("/v1/tools/check_availability", json=body)


async def book(client, start=f"{TUESDAY}T18:00:00", service="RCT consultation", **body):
    body = {"service": service, "start_at": start, "customer_name": "Ravi", "phone": PHONE, **body}
    return await client.post("/v1/tools/create_booking", json=body)


async def change(client, booking_id, action="reschedule", **body):
    body = {"booking_id": booking_id, "action": action, **body}
    return await client.post("/v1/tools/reschedule_or_cancel", json=body)


# check_availability ---------------------------------------------------------


async def test_evening_slots_tomorrow(client):
    r = await availability(client, preferred_time="evening")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["date"] == TUESDAY and data["note"] is None
    assert data["price_inr"] == 500 and data["duration_min"] == 30
    assert times(data["slots"]) == ["17:00", "17:30", "18:00"]
    assert {s["staff"] for s in data["slots"]} == {"Dr. Lakshmi Reddy"}  # Arjun doesn't do RCT


async def test_today_starts_after_opening(client):
    data = (await availability(client, date="2026-11-02", preferred_time="morning")).json()
    assert times(data["slots"]) == ["10:00", "10:30", "11:00"]


async def test_lead_time_pushes_to_other_part_of_day(client, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 2, 13, 10, tzinfo=IST))
    data = (await availability(client, date="2026-11-02", preferred_time="morning")).json()
    assert times(data["slots"]) == ["17:00", "17:30", "18:00"]
    assert "None of these are in the requested time (morning)" in data["note"]


async def test_closed_day_moves_to_next_open_day(client):
    data = (await availability(client, date="2026-11-08")).json()  # Sunday
    assert data["date"] == "2026-11-09"
    assert (
        data["note"] == "Nothing free on Sunday 8 November. The next free day is Monday 9 November."
    )


async def test_holiday_block_is_respected(client, clinic):
    async with system_session() as s:
        s.add(
            BlockedSlot(
                business_id=clinic,
                start_at=datetime(2026, 11, 3, 0, 0, tzinfo=IST),
                end_at=datetime(2026, 11, 4, 0, 0, tzinfo=IST),
                reason="Diwali",
            )
        )
    assert (await availability(client)).json()["date"] == "2026-11-04"


async def test_staff_who_doesnt_do_the_service(client):
    r = await availability(client, staff="Arjun")
    assert r.status_code == 422
    assert r.json()["staff"] == ["Dr. Lakshmi Reddy"]


async def test_unknown_service_lists_real_ones(client):
    r = await availability(client, service="Hair cut")
    assert r.status_code == 422
    assert "Teeth cleaning" in r.json()["services"]


async def test_past_date_rejected(client):
    assert (await availability(client, date="2026-11-01")).status_code == 422


# create_booking / find_booking --------------------------------------------


async def test_book_and_find(client):
    r = await book(client)
    assert r.status_code == 200, r.text
    booking = r.json()
    assert booking["label"] == "Tue 3 Nov, 6:00 PM"
    assert booking["staff"] == "Dr. Lakshmi Reddy"
    assert booking["start_at"] == "2026-11-03T18:00:00+05:30"

    found = await client.post("/v1/tools/find_booking", json={"phone": "+91 98765 43210"})
    assert [b["booking_id"] for b in found.json()["bookings"]] == [booking["booking_id"]]


async def test_same_slot_twice_is_refused_with_alternatives(client):
    assert (await book(client)).status_code == 200
    r = await book(client, customer_name="Sita", phone="9123456789")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "slot_unavailable"
    assert times(body["alternatives"]) == ["17:15", "17:30", "18:30"]


async def test_second_staff_member_takes_overlapping_booking(client):
    first = await book(client, service="General consultation")
    second = await book(client, service="General consultation", phone="9123456789")
    third = await book(client, service="General consultation", phone="9000000000")
    assert {first.json()["staff"], second.json()["staff"]} == {"Dr. Arjun Rao", "Dr. Lakshmi Reddy"}
    assert third.status_code == 409


async def test_concurrent_requests_for_one_slot_book_exactly_once(client):
    attempts = [
        book(client, customer_name=f"Caller {i}", phone=f"98765432{i:02d}") for i in range(5)
    ]
    codes = sorted(r.status_code for r in await asyncio.gather(*attempts))
    assert codes == [200, 409, 409, 409, 409]


async def test_outside_hours_refused(client):
    r = await book(client, start=f"{TUESDAY}T14:00:00")
    assert r.status_code == 409
    assert r.json()["alternatives"]


async def test_past_time_refused(client):
    assert (await book(client, start="2026-11-02T08:00:00")).status_code == 422


async def test_bad_phone_refused(client):
    r = await book(client, phone="12345")
    assert r.status_code == 422
    assert "phone" in r.json()["message"]


# reschedule_or_cancel ---------------------------------------------------------


async def test_reschedule_frees_the_old_slot(client):
    booking = (await book(client)).json()
    r = await change(client, booking["booking_id"], new_start_at="2026-11-04T10:30:00")
    assert r.status_code == 200, r.text
    assert r.json()["label"] == "Wed 4 Nov, 10:30 AM"
    assert (await book(client, customer_name="Sita", phone="9123456789")).status_code == 200


async def test_reschedule_can_overlap_its_own_old_time(client):
    booking = (await book(client)).json()
    r = await change(client, booking["booking_id"], new_start_at=f"{TUESDAY}T18:15:00")
    assert r.status_code == 200, r.text


async def test_reschedule_into_a_taken_slot_refused(client):
    await book(client, start=f"{TUESDAY}T17:00:00", phone="9123456789")
    booking = (await book(client)).json()
    r = await change(client, booking["booking_id"], new_start_at=f"{TUESDAY}T17:00:00")
    assert r.status_code == 409


async def test_cancel_reopens_slot_and_cannot_repeat(client):
    booking = (await book(client)).json()
    assert (await change(client, booking["booking_id"], "cancel")).json()["status"] == "cancelled"
    assert (await change(client, booking["booking_id"], "cancel")).status_code == 422
    assert (await book(client, phone="9123456789")).status_code == 200


async def test_verified_caller_cannot_change_someone_elses_booking(client):
    booking = (await book(client)).json()
    r = await change(client, booking["booking_id"], "cancel", caller_phone="9123456789")
    assert r.status_code == 404
    r = await change(client, booking["booking_id"], "cancel", caller_phone=PHONE)
    assert r.status_code == 200


# search_knowledge / handoff_to_human -----------------------------------------


async def test_knowledge_search_finds_the_faq(client):
    r = await client.post("/v1/tools/search_knowledge", json={"question": "Is there parking?"})
    assert r.json()["results"][0]["title"] == "Location and parking"
    r = await client.post("/v1/tools/search_knowledge", json={"question": "can I pay by UPI"})
    assert r.json()["results"][0]["title"] == "Payment methods"


async def test_knowledge_search_admits_when_it_has_nothing(client):
    r = await client.post("/v1/tools/search_knowledge", json={"question": "Do you sell bicycles?"})
    assert r.json()["results"] == []
    assert "Say so" in r.json()["note"]


async def test_conversation_lifecycle_with_handoff(client, clinic):
    conv = (
        await client.post(
            "/v1/conversations", json={"channel": "whatsapp", "customer_phone": PHONE}
        )
    ).json()
    assert conv["customer_phone"] == "+919876543210"

    turn = {
        "messages": [{"role": "user", "text": "I want to talk to the doctor"}],
        "outcome": "handoff",
        "llm_input_tokens": 1200,
        "llm_output_tokens": 80,
        "cost_inr": 0.0134,
    }
    r = await client.post(f"/v1/conversations/{conv['id']}/turns", json=turn)
    assert r.json() == {"saved": 1}

    r = await client.post(
        "/v1/tools/handoff_to_human",
        json={
            "reason": "asked for doctor",
            "summary": "wants a call",
            "conversation_id": conv["id"],
        },
    )
    assert r.json()["ok"] is True

    r = await client.post(f"/v1/conversations/{conv['id']}/end", json={})
    assert r.status_code == 200

    async with system_session() as s:
        row = await s.scalar(select(Conversation).where(Conversation.id == conv["id"]))
    assert row.handoff and row.handoff_reason == "asked for doctor"
    assert row.outcome == "handoff" and float(row.cost_inr) == 0.0134
    assert row.llm_input_tokens == 1200
    assert row.ended_at is not None and row.customer_id is not None
