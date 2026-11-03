"""Tool declarations the LLM sees, and the fields the runtime fills in itself.

The LLM chooses the tool and the conversational arguments. Anything it must not
control (which conversation this is, the channel, a verified caller number) is
added in prepare_args after the model has decided.
"""

from dataclasses import dataclass

TOOLS: list[dict] = [
    {
        "name": "search_knowledge",
        "description": (
            "Search the business's FAQs and documents. Use for any question about policies, "
            "location, payment, procedures, etc. Write the question in English."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question, in English"}
            },
            "required": ["question"],
        },
    },
    {
        "name": "check_availability",
        "description": "Find up to 3 free slots for a service on a date (or the next free day).",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Exact service name from the list"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "preferred_time": {
                    "type": "string",
                    "description": "morning, afternoon, evening, any, or a time like 18:15",
                },
                "staff": {"type": "string", "description": "Only if the customer asks for someone"},
            },
            "required": ["service", "date"],
        },
    },
    {
        "name": "create_booking",
        "description": (
            "Book a slot returned by check_availability. Only call after the customer has "
            "confirmed service, date, time and name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "start_at": {
                    "type": "string",
                    "description": "Slot start_at exactly as check_availability returned it",
                },
                "customer_name": {"type": "string"},
                "phone": {"type": "string", "description": "Customer's mobile number"},
                "staff": {"type": "string"},
            },
            "required": ["service", "start_at", "customer_name", "phone"],
        },
    },
    {
        "name": "find_booking",
        "description": "List the customer's upcoming bookings, to reschedule or cancel them.",
        "parameters": {
            "type": "object",
            "properties": {"phone": {"type": "string"}},
            "required": ["phone"],
        },
    },
    {
        "name": "reschedule_or_cancel",
        "description": (
            "Move or cancel a booking found with find_booking. Confirm with the customer first. "
            "For reschedule, check_availability for the new time before calling this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string"},
                "action": {"type": "string", "enum": ["reschedule", "cancel"]},
                "new_start_at": {"type": "string", "description": "Required for reschedule"},
            },
            "required": ["booking_id", "action"],
        },
    },
    {
        "name": "handoff_to_human",
        "description": (
            "Ask the team to call the customer back. Use when they ask for a person, are upset, "
            "need medical advice, or you couldn't help after 2 tries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "summary": {"type": "string", "description": "What the customer needs, for staff"},
            },
            "required": ["reason", "summary"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}


@dataclass(frozen=True)
class ToolContext:
    conversation_id: str
    channel: str  # voice | whatsapp | web_chat
    verified_phone: str | None = None  # from caller ID or WhatsApp, never from the LLM


def prepare_args(name: str, args: dict, ctx: ToolContext) -> dict:
    args = dict(args)
    if name == "create_booking":
        args["source"] = ctx.channel
        args["conversation_id"] = ctx.conversation_id
        if ctx.verified_phone:
            args["phone"] = ctx.verified_phone
    elif name == "find_booking" and ctx.verified_phone:
        # Otherwise anyone could read anyone's bookings by saying a number.
        args["phone"] = ctx.verified_phone
    elif name == "reschedule_or_cancel" and ctx.verified_phone:
        args["caller_phone"] = ctx.verified_phone
    elif name == "handoff_to_human":
        args["conversation_id"] = ctx.conversation_id
    return args
