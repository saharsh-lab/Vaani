"""Builds the per-business system prompt at the start of each conversation.

Kept short on purpose: facts that change or run long live in the knowledge base
and are fetched with search_knowledge.
"""

from datetime import datetime, time, timedelta

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LANGUAGE_NAMES = {"te": "Telugu", "hi": "Hindi", "en": "English", "ta": "Tamil", "kn": "Kannada"}
CHANNELS = {"voice": "a voice call", "whatsapp": "WhatsApp", "web_chat": "the website chat"}
# Text-to-speech reads each language best in its own script.
SCRIPTS = {"te": "Telugu script", "hi": "Devanagari", "ta": "Tamil script", "kn": "Kannada script"}


def voice_greeting_instructions(ctx: dict) -> str:
    """What the voice agent says first. Greetings are often typed in English letters
    ("Namaskaram! ... swagatam"), and the model copies them as written, which the
    text-to-speech then reads with an English accent."""
    code = ctx["languages"][0] if ctx["languages"] else "en"
    language = LANGUAGE_NAMES.get(code, "English")
    script = SCRIPTS.get(code)
    return f"Greet the caller now, in {language}" + (f", written in {script}." if script else ".")


def _clock(t: time) -> str:
    hour = t.hour % 12 or 12
    return f"{hour}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def summarize_hours(hours: list[dict]) -> list[str]:
    """[{weekday, open_time, close_time}] -> ["Mon-Sat: 10:00 AM-1:30 PM, 5:00 PM-9:00 PM", "Sun: closed"]"""
    by_day: dict[int, str] = {}
    for h in sorted(hours, key=lambda h: (h["weekday"], h["open_time"])):
        span = f"{_clock(time.fromisoformat(h['open_time']))}-{_clock(time.fromisoformat(h['close_time']))}"
        by_day[h["weekday"]] = f"{by_day[h['weekday']]}, {span}" if h["weekday"] in by_day else span

    lines: list[str] = []
    day = 0
    while day < 7:
        text = by_day.get(day, "closed")
        end = day
        while end + 1 < 7 and by_day.get(end + 1, "closed") == text:
            end += 1
        days = WEEKDAYS[day] if day == end else f"{WEEKDAYS[day]}-{WEEKDAYS[end]}"
        lines.append(f"{days}: {text}")
        day = end + 1
    return lines


def date_guide(now: datetime, days: int = 14) -> str:
    """The next two weeks as a lookup table. Models get weekday-to-date maths wrong
    (e.g. "Thursday" -> the wrong month); reading the date off a list fixes that."""
    names = {0: "today", 1: "tomorrow", 2: "day after tomorrow"}
    lines = []
    for i in range(days):
        d = now.date() + timedelta(days=i)
        label = names.get(i) or ("next " + f"{d:%A}" if i >= 7 else f"this {d:%A}")
        lines.append(f"- {d:%a %d %b} = {d.isoformat()} ({label})")
    return "\n".join(lines)


def build_system_prompt(ctx: dict, *, channel: str, verified_phone: str | None) -> str:
    now = datetime.fromisoformat(ctx["now_local"])
    languages = ", ".join(LANGUAGE_NAMES.get(code, code) for code in ctx["languages"])
    services = "\n".join(
        f"- {s['name']}: {s['duration_min']} min"
        + (f", ₹{s['price_inr']:g}" if s["price_inr"] is not None else "")
        + (f" ({s['description']})" if s.get("description") else "")
        for s in ctx["services"]
    )
    hours = "\n".join(f"- {line}" for line in summarize_hours(ctx["hours"]))
    if verified_phone:
        caller = (
            f"The customer's number is {verified_phone}, verified by the {channel} channel. "
            "Use it for bookings; don't ask for it."
        )
    else:
        caller = "You don't know the customer's number. Ask for their mobile number before booking."
        if channel == "voice":
            caller += " Read it back digit by digit to confirm."

    greeting = ctx.get("greeting") or "Hello, how can I help?"
    if channel == "whatsapp":
        opening = (
            f'The customer messaged first. Start your first reply with a short greeting like "{greeting}".\n'
            "Messages starting with [voice note] were transcribed from speech and may contain "
            "recognition mistakes: confirm names, dates, times and numbers before acting on them, "
            "and reply in the language they spoke."
        )
    elif channel == "voice":
        opening = (
            f'The call has just connected. Greet the caller first, briefly, like "{greeting}", '
            "written in that language's own script. Greet only once; after that, get straight "
            "to what they need. When they ask for an appointment and you know the service and "
            "day, check availability right away instead of asking whether to."
        )
    else:
        opening = f'You have already greeted them with: "{greeting}"'

    if channel == "voice":
        script_rule = (
            "Reply in the language the caller speaks and switch when they switch. Your replies "
            "are turned into speech, so write Telugu in Telugu script and Hindi in Devanagari, "
            "keeping English words (like appointment, slot, doctor) in English letters."
        )
    else:
        script_rule = (
            "Reply in the language and script the customer uses. Romanised Telugu or Hindi mixed "
            'with English (like "repu evening slot undi") is normal; answer the same way. '
            "Switch when they switch."
        )

    if channel == "voice":
        length_rule = (
            "Keep replies to 1-2 short sentences. No markdown, lists or emoji: replies are spoken aloud. "
            'Say dates and times the way people say them ("tomorrow", "Friday the 6th", "5:30 in the '
            'evening"), never like 2026-11-06. When you use a tool, call it straight away without '
            'saying anything first: the caller hears "one moment" automatically.'
        )
    else:
        length_rule = "Keep replies short, 1-3 sentences, in plain text without markdown."

    return f"""You are the receptionist for {ctx["name"]}, a {ctx["type"]}{f" at {ctx['address']}" if ctx.get("address") else ""}. You're talking with a customer over {CHANNELS[channel]}.

It is {now:%A}, {now:%d %B %Y}, {_clock(now.time())} ({ctx["timezone"]}). Take dates from this list, never calculate them; pass them to tools as YYYY-MM-DD:
{date_guide(now)}

Opening hours:
{hours}

Services (use these exact names in tools):
{services}

Staff: {", ".join(ctx["staff"])}

Languages: {languages}. {script_rule}

{opening}
{caller}

Rules:
1. Only state facts from this prompt or a tool result. Never guess prices, times, slots or policies. If search_knowledge finds nothing, say you don't know and offer a callback from the team.
2. Always check_availability before offering times. Offer at most 3.
3. Before create_booking or reschedule_or_cancel, read back the service, day, time and name and ask the customer to confirm. Only act on a clear yes in their next message: never book, cancel or change a booking in the same reply where you look it up.
4. If asked for medical, legal or financial advice (which medicine to take, what a symptom means), say you can't advise on that and offer an appointment or a callback from the team.
5. Use handoff_to_human if they ask for a person, are upset, or you've failed to help twice.
6. {length_rule}
7. After booking, repeat the day and time.
8. Opening hours, prices, durations, services and staff are listed above: answer those directly. Use search_knowledge for anything else."""
