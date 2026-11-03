"""Browser voice calls.

POST /v1/voice/session  gives the browser a short-lived LiveKit token for a new
                        room. The token tells LiveKit to dispatch the voice agent
                        into that room, with the business id as job metadata.
GET  /voice/{slug}      the "Talk to us" page; businesses embed it in an iframe.

Both are public (the widget runs on the business's own website), so session
creation is rate-limited per IP and every call has a maximum length.
"""

import html
import json
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from livekit import api as livekit
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import system_session
from app.models import Business
from app.ratelimit import RateLimiter
from vaani_agent.config import VOICE_AGENT_NAME, get_agent_settings

router = APIRouter(tags=["voice"])

WIDGET = Path(__file__).resolve().parent.parent / "static" / "voice.html"


class VoiceSessionIn(BaseModel):
    business: str = Field(description="Business slug, e.g. sri-dental")


class VoiceSessionOut(BaseModel):
    server_url: str
    participant_token: str
    room_name: str


limiter = RateLimiter()


async def _business(slug: str) -> Business | None:
    async with system_session() as session:
        return await session.scalar(select(Business).where(Business.slug == slug))


@router.post("/v1/voice/session")
async def create_voice_session(body: VoiceSessionIn, request: Request) -> VoiceSessionOut:
    settings = get_agent_settings()
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.allow(client_ip, settings.voice_calls_per_ip_per_hour):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many calls. Try again later.")
    business = await _business(body.business)
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown business")

    room = f"call-{business.slug}-{uuid.uuid4().hex[:10]}"
    dispatch = livekit.RoomAgentDispatch(
        agent_name=VOICE_AGENT_NAME, metadata=json.dumps({"business_id": str(business.id)})
    )
    token = (
        livekit.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(f"caller-{uuid.uuid4().hex[:12]}")
        .with_name("Caller")
        .with_ttl(timedelta(minutes=10))  # time to join; the call itself is capped separately
        .with_grants(
            livekit.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(livekit.RoomConfiguration(agents=[dispatch]))
        .to_jwt()
    )
    return VoiceSessionOut(
        server_url=settings.livekit_public_url or settings.livekit_url,
        participant_token=token,
        room_name=room,
    )


@router.get("/voice/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def voice_page(slug: str) -> HTMLResponse:
    business = await _business(slug)
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown business")
    page = (
        WIDGET.read_text(encoding="utf-8")
        .replace("{{BUSINESS_NAME}}", html.escape(business.name))
        .replace("{{BUSINESS_SLUG_JSON}}", json.dumps(business.slug))
    )
    return HTMLResponse(page)
