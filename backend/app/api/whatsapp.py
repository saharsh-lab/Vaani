"""WhatsApp Cloud API webhook.

GET  verifies the subscription when you save the webhook in Meta's dashboard.
POST receives messages. It checks Meta's signature, finds the business from the
receiving number, skips messages already accepted, and returns 200 at once; the
agent turn runs in the background so Meta doesn't time out and retry.
"""

import hmac
import json
import logging
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import system_session
from app.models import Business, ChannelEvent
from app.phones import mask_phone
from vaani_agent.api_client import VaaniApi
from vaani_agent.config import get_agent_settings
from vaani_agent.runtime import AgentSession
from vaani_agent.speech import SarvamSTT
from vaani_agent.whatsapp import (
    InboundMessage,
    WhatsAppAgent,
    WhatsAppClient,
    delivery_statuses,
    parse_webhook,
    verify_signature,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])


def get_whatsapp_agent(request: Request) -> WhatsAppAgent:
    agent = getattr(request.app.state, "whatsapp_agent", None)
    if agent is None:
        settings = get_agent_settings()
        if not settings.gemini_api_key:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GEMINI_API_KEY is not set")
        app = request.app

        def api_for(business_id: str) -> VaaniApi:
            # In-process HTTP: tool calls still go through the API routes, auth and
            # tenant checks, without a network hop.
            return VaaniApi(
                "http://vaani.internal",
                get_settings().agent_api_key,
                business_id,
                transport=httpx.ASGITransport(app=app),
            )

        agent = WhatsAppAgent(
            settings=settings,
            llm=AgentSession.gemini_client(settings),
            whatsapp=WhatsAppClient(
                settings.whatsapp_access_token, settings.whatsapp_graph_version
            ),
            api_for=api_for,
            stt=SarvamSTT(
                settings.sarvam_api_key,
                model=settings.sarvam_stt_model,
                mode=settings.sarvam_stt_mode,
            )
            if settings.sarvam_api_key
            else None,
        )
        request.app.state.whatsapp_agent = agent
    return agent


async def claim(message: InboundMessage) -> uuid.UUID | None:
    """The business this message is for, or None if the number is unknown or the
    message was already accepted (Meta can deliver a webhook more than once)."""
    async with system_session() as session:
        business_id = await session.scalar(
            select(Business.id).where(Business.whatsapp_phone_number_id == message.phone_number_id)
        )
        if business_id is None:
            log.warning("whatsapp message for unknown number id %s", message.phone_number_id)
            return None
        is_new = await session.scalar(
            insert(ChannelEvent)
            .values(business_id=business_id, channel="whatsapp", external_id=message.message_id)
            .on_conflict_do_nothing()
            .returning(ChannelEvent.external_id)
        )
    return business_id if is_new else None


@router.get("")
async def verify_webhook(
    mode: Annotated[str, Query(alias="hub.mode")],
    token: Annotated[str, Query(alias="hub.verify_token")],
    challenge: Annotated[str, Query(alias="hub.challenge")],
) -> PlainTextResponse:
    expected = get_agent_settings().whatsapp_verify_token
    if (
        mode != "subscribe"
        or not expected
        or not hmac.compare_digest(token.encode(), expected.encode())
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook verification failed")
    return PlainTextResponse(challenge)


@router.post("")
async def receive(
    request: Request,
    background: BackgroundTasks,
    agent: Annotated[WhatsAppAgent, Depends(get_whatsapp_agent)],
) -> dict:
    secret = get_agent_settings().whatsapp_app_secret
    if not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WHATSAPP_APP_SECRET is not set")
    body = await request.body()
    if not verify_signature(secret, body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON") from exc

    for report in delivery_statuses(payload):
        who = mask_phone("+" + report.recipient)
        if report.errors:
            log.warning(
                "WhatsApp couldn't deliver a reply to %s: %s", who, "; ".join(report.errors)
            )
        else:
            log.info("WhatsApp reply to %s: %s", who, report.status)

    accepted = 0
    for message in parse_webhook(payload):
        business_id = await claim(message)
        if business_id:
            background.add_task(agent.handle, str(business_id), message)
            accepted += 1
    return {"accepted": accepted}
