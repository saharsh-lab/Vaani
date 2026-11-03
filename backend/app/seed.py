"""Demo tenant: Sri Dental Clinic, a fictional clinic in Hyderabad.

    python -m app.seed            # (re)creates the demo business
    python -m app.seed --slug x   # same data under another slug
    python -m app.seed --whatsapp-number-id 1234567890   # answer this WhatsApp number
    python -m app.seed --demo-activity   # plus a week of sample bookings and conversations

Also creates two dashboard logins (printed at the end). Re-running deletes and
recreates the business, including its bookings.
"""

import argparse
import asyncio
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import system_session
from app.models import (
    Booking,
    Business,
    Conversation,
    Customer,
    KbChunk,
    KbDocument,
    Message,
    Service,
    Staff,
    StaffService,
    User,
    WorkingHours,
)

SERVICES = [
    # name, minutes, price (INR), description
    ("General consultation", 15, 300, "Check-up and advice for any dental problem"),
    ("RCT consultation", 30, 500, "Assessment before root canal treatment"),
    ("Teeth cleaning", 45, 1200, "Scaling and polishing"),
    ("Tooth extraction", 30, 1500, "Simple extraction; complex cases need a consultation first"),
    ("Braces consultation", 30, 500, "Orthodontic assessment for braces or aligners"),
]

FAQS = [
    (
        "Location and parking",
        "Q: Where is the clinic and is there parking? A: Plot 42, Road No. 3, Banjara Hills, "
        "Hyderabad, above the Apollo Pharmacy. Free two-wheeler parking in front; car parking "
        "on the street.",
    ),
    (
        "Payment methods",
        "Q: How can I pay? A: We accept UPI, debit and credit cards, and cash. Payment is "
        "collected after the appointment.",
    ),
    (
        "Insurance",
        "Q: Do you take insurance? A: We don't offer cashless insurance. We give an itemised bill "
        "you can submit to your insurer for reimbursement.",
    ),
    (
        "Emergencies",
        "Q: What if I have a dental emergency? A: During clinic hours, come in directly and we "
        "will see you between appointments. After hours, leave a message and the doctor will "
        "call back.",
    ),
    (
        "Children",
        "Q: Do you treat children? A: Yes, we see children from age 3. A parent must come along.",
    ),
    (
        "What to bring",
        "Q: What should I bring to my appointment? A: Bring any previous X-rays, prescriptions, "
        "and a list of medicines you take. Arrive 10 minutes early on your first visit.",
    ),
    (
        "Cancellation policy",
        "Q: Can I cancel or reschedule? A: Yes, free of charge. Please tell us at least 2 hours "
        "before your appointment.",
    ),
    (
        "Root canal treatment",
        "Q: How many visits does a root canal take, and what does it cost? A: Usually 2 to 3 "
        "visits. The cost depends on the tooth and is confirmed at the RCT consultation, which "
        "costs 500 rupees.",
    ),
]


async def seed_demo(
    session: AsyncSession,
    slug: str = "sri-dental",
    name: str = "Sri Dental Clinic",
    whatsapp_phone_number_id: str | None = None,
) -> uuid.UUID:
    await session.execute(delete(Business).where(Business.slug == slug))

    business = Business(
        slug=slug,
        name=name,
        type="dental clinic",
        timezone="Asia/Kolkata",
        languages=["te", "hi", "en"],
        greeting=f"Namaskaram! {name} ki swagatam. Meeku ela help cheyagalanu?",
        phone="+914023456789",
        address="Plot 42, Road No. 3, Banjara Hills, Hyderabad",
        whatsapp_phone_number_id=whatsapp_phone_number_id,
    )
    session.add(business)
    await session.flush()
    bid = business.id

    services = {
        n: Service(business_id=bid, name=n, duration_min=m, price_inr=p, description=d)
        for n, m, p, d in SERVICES
    }
    lakshmi = Staff(business_id=bid, name="Dr. Lakshmi Reddy")
    arjun = Staff(business_id=bid, name="Dr. Arjun Rao")
    session.add_all([*services.values(), lakshmi, arjun])
    await session.flush()

    # Dr. Lakshmi does everything; Dr. Arjun doesn't do RCT or braces.
    links = [(lakshmi, s) for s in services.values()]
    links += [
        (arjun, services[n]) for n in ("General consultation", "Teeth cleaning", "Tooth extraction")
    ]
    session.add_all(
        StaffService(business_id=bid, staff_id=st.id, service_id=sv.id) for st, sv in links
    )

    # Clinic hours Mon-Sat, split shift; closed Sunday. Dr. Arjun works evenings only.
    for weekday in range(6):
        session.add(
            WorkingHours(
                business_id=bid, weekday=weekday, open_time=time(10), close_time=time(13, 30)
            )
        )
        session.add(
            WorkingHours(business_id=bid, weekday=weekday, open_time=time(17), close_time=time(21))
        )
        session.add(
            WorkingHours(
                business_id=bid,
                staff_id=arjun.id,
                weekday=weekday,
                open_time=time(17),
                close_time=time(21),
            )
        )

    for title, content in FAQS:
        doc = KbDocument(business_id=bid, title=title, source_type="faq")
        session.add(doc)
        await session.flush()
        session.add(KbChunk(business_id=bid, document_id=doc.id, content=content))

    await session.flush()
    return bid


DEMO_PASSWORDS = {"owner": "vaani-demo-owner", "staff": "vaani-demo-staff"}


async def add_demo_logins(
    session: AsyncSession, business_id: uuid.UUID, slug: str
) -> dict[str, str]:
    """An owner and a staff login for the demo business. Returns {email: password}."""
    from app.auth import hash_password

    logins = {}
    for role, name in (("owner", "Dr. Lakshmi Reddy"), ("staff", "Anitha (front desk)")):
        email = f"{role}@{slug}.example.com"
        await session.execute(delete(User).where(User.email == email))
        session.add(
            User(
                business_id=business_id,
                email=email,
                name=name,
                role=role,
                password_hash=hash_password(DEMO_PASSWORDS[role]),
            )
        )
        logins[email] = DEMO_PASSWORDS[role]
    await session.flush()
    return logins


async def add_demo_activity(session: AsyncSession, business_id: uuid.UUID) -> None:
    """Sample bookings and conversations across the coming week, so the dashboard
    has something to show before real customers call. Demo business only."""
    now = (
        clock.now().astimezone(ZoneInfo("Asia/Kolkata")).replace(minute=0, second=0, microsecond=0)
    )
    services = {
        s.name: s
        for s in (
            await session.scalars(select(Service).where(Service.business_id == business_id))
        ).all()
    }
    staff = {
        s.name: s
        for s in (
            await session.scalars(select(Staff).where(Staff.business_id == business_id))
        ).all()
    }
    people = [
        ("Ravi Kumar", "+919876543210", "te-IN"),
        ("Priya Sharma", "+919123456780", "hi-IN"),
        ("Anil Reddy", "+919988776655", "en-IN"),
        ("Meena Rao", "+919000011111", "te-IN"),
    ]
    customers = []
    for name, phone, lang in people:
        c = Customer(business_id=business_id, name=name, phone=phone, preferred_language=lang)
        session.add(c)
        customers.append(c)
    await session.flush()

    def at(day: int, hour: int, minute: int = 0) -> datetime:
        return (now + timedelta(days=day)).replace(hour=hour, minute=minute)

    plan = [  # (day offset, hour, minute, service, doctor, customer, source)
        (0, 17, 0, "General consultation", "Dr. Arjun Rao", 0, "voice"),
        (0, 18, 0, "RCT consultation", "Dr. Lakshmi Reddy", 1, "whatsapp"),
        (1, 10, 30, "Teeth cleaning", "Dr. Lakshmi Reddy", 2, "voice"),
        (1, 18, 15, "Tooth extraction", "Dr. Arjun Rao", 3, "dashboard"),
        (2, 11, 0, "Braces consultation", "Dr. Lakshmi Reddy", 0, "whatsapp"),
        (3, 17, 30, "General consultation", "Dr. Arjun Rao", 2, "voice"),
    ]
    for day, hour, minute, service, doctor, who, source in plan:
        start = at(day, hour, minute)
        session.add(
            Booking(
                business_id=business_id,
                customer_id=customers[who].id,
                service_id=services[service].id,
                staff_id=staff[doctor].id,
                start_at=start,
                end_at=start + timedelta(minutes=services[service].duration_min),
                source=source,
                customer_name=people[who][0],
            )
        )

    calls = [
        (
            customers[0],
            "voice",
            "te-IN",
            "booked",
            94,
            Decimal("0.6120"),
            False,
            None,
            [
                ("user", "రేపు సాయంత్రం general consultation కావాలి", None),
                ("tool", None, "check_availability"),
                ("assistant", "రేపు సాయంత్రం 5, 5:30 లేదా 6 కి slot ఉంది. ఏది కావాలి?", 910),
                ("user", "5 కి, నా పేరు రవి", None),
                ("tool", None, "create_booking"),
                ("assistant", "రవి గారు, రేపు సాయంత్రం 5 కి Dr. Arjun Rao తో booked.", 1040),
            ],
        ),
        (
            customers[1],
            "whatsapp",
            "hi-IN",
            "booked",
            180,
            Decimal("0.0310"),
            False,
            None,
            [
                ("user", "Kal shaam RCT consultation mil sakta hai?", None),
                ("tool", None, "check_availability"),
                (
                    "assistant",
                    "Kal shaam 6 baje Dr. Lakshmi ke saath slot hai. Book kar doon?",
                    None,
                ),
                ("user", "Haan please, Priya Sharma", None),
                ("tool", None, "create_booking"),
                ("assistant", "Ho gaya! Kal shaam 6 baje, Dr. Lakshmi Reddy.", None),
            ],
        ),
        (
            customers[3],
            "voice",
            "en-IN",
            "handoff",
            61,
            Decimal("0.4410"),
            True,
            "Asked to speak to the doctor about pain after an extraction",
            [
                (
                    "user",
                    "I had a tooth pulled yesterday and it's still bleeding. Can I talk to the doctor?",
                    None,
                ),
                ("tool", None, "handoff_to_human"),
                ("assistant", "I've asked the team to call you back right away.", 980),
            ],
        ),
    ]
    for customer, channel, lang, outcome, seconds, cost, handoff, reason, lines in calls:
        started = now - timedelta(hours=2)
        convo = Conversation(
            business_id=business_id,
            customer_id=customer.id,
            channel=channel,
            language=lang,
            started_at=started,
            last_activity_at=started + timedelta(seconds=seconds),
            ended_at=started + timedelta(seconds=seconds),
            duration_s=seconds,
            outcome=outcome,
            cost_inr=cost,
            handoff=handoff,
            handoff_reason=reason,
            handoff_status="open" if handoff else None,
            summary=reason,
        )
        session.add(convo)
        await session.flush()
        for role, line, extra in lines:  # extra: tool name for tool lines, latency for replies
            tool = extra if role == "tool" else None
            session.add(
                Message(
                    business_id=business_id,
                    conversation_id=convo.id,
                    role=role,
                    text=line,
                    tool_name=tool,
                    tool_args={} if tool else None,
                    tool_result={"ok": True} if tool else None,
                    latency_ms=extra if role == "assistant" else None,
                )
            )
    await session.flush()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--slug", default="sri-dental")
    parser.add_argument(
        "--whatsapp-number-id", help="Phone number ID from Meta's WhatsApp > API Setup page"
    )
    parser.add_argument(
        "--demo-activity", action="store_true", help="add sample bookings and conversations"
    )
    args = parser.parse_args()
    async with system_session() as session:
        bid = await seed_demo(
            session, slug=args.slug, whatsapp_phone_number_id=args.whatsapp_number_id
        )
        logins = await add_demo_logins(session, bid, args.slug)
        if args.demo_activity:
            await add_demo_activity(session, bid)
    print(f"Seeded {args.slug} (business id {bid})")
    print("Dashboard logins (demo only; change them anywhere public):")
    for email, password in logins.items():
        print(f"  {email}  /  {password}")


if __name__ == "__main__":
    asyncio.run(main())
