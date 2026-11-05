"""WhatsApp channel: parse Cloud API webhooks, run the agent, send the reply.

Each inbound message is one turn. The agent's history is saved after every turn
and restored on the next message, so a chat can span many webhook calls. Voice
notes are downloaded from Meta and transcribed with Sarvam before the turn.
"""

import asyncio
import hashlib
import hmac
import logging
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from vaani_agent.api_client import VaaniApi
from vaani_agent.config import AgentSettings
from vaani_agent.runtime import AgentSession, VoiceNote
from vaani_agent.speech import SarvamSTT, SpeechError, keyterms_for, ogg_opus_duration
from vaani_agent.tools import ToolContext

log = logging.getLogger(__name__)

# Sent without the LLM, so they're written in all three languages.
UNSUPPORTED_REPLY = (
    "Sorry, I can't open this kind of message. Please type your question. "
    "Kshaminchandi, ee message open cheyalekapotunnanu, dayachesi type cheyandi. "
    "Maaf kijiye, yeh message nahi khul raha, kripya apna sawaal type karein."
)
VOICE_TOO_LONG_REPLY = (
    "Your voice note is a bit long for me. Please send one under 30 seconds, or type your message. "
    "Dayachesi 30 seconds lopu voice note pampandi, leda type cheyandi. "
    "Kripya 30 second se chhota voice note bhejein, ya type karein."
)
VOICE_NOT_UNDERSTOOD_REPLY = (
    "Sorry, I couldn't make out that voice note. Please send it again or type your message. "
    "Kshaminchandi, voice note ardham kaaledu, malli pampandi leda type cheyandi. "
    "Maaf kijiye, voice note samajh nahi aaya, dobara bhejein ya type karein."
)
ERROR_REPLY = "Sorry, something went wrong on our side. Please try again in a minute."


class MediaTooLarge(Exception):
    pass


@dataclass(frozen=True)
class InboundMessage:
    phone_number_id: str  # the business's WhatsApp number (Meta id)
    wa_id: str  # sender's number, digits only, e.g. 919876543210
    message_id: str  # wamid..., unique per message
    text: str | None  # typed text, button title; None for media
    profile_name: str | None = None
    audio_id: str | None = None  # Meta media id of a voice note or audio file
    audio_mime: str | None = None

    @property
    def sender_phone(self) -> str:
        return f"+{self.wa_id}"


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Meta signs each webhook body: X-Hub-Signature-256: sha256=<hex HMAC>."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), expected)


def _text_of(message: dict) -> str | None:
    kind = message.get("type")
    if kind == "text":
        return message.get("text", {}).get("body")
    if kind == "button":  # quick-reply button on a template
        return message.get("button", {}).get("text")
    if kind == "interactive":
        reply = message.get("interactive", {})
        return (reply.get("button_reply") or reply.get("list_reply") or {}).get("title")
    return None


def parse_webhook(payload: dict) -> list[InboundMessage]:
    """Customer messages in a webhook. Delivery/read status updates are skipped."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            number_id = value.get("metadata", {}).get("phone_number_id")
            names = {
                c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])
            }
            for m in value.get("messages", []):
                if not number_id or not m.get("from") or not m.get("id"):
                    continue
                audio = m.get("audio", {}) if m.get("type") == "audio" else {}
                messages.append(
                    InboundMessage(
                        phone_number_id=number_id,
                        wa_id=m["from"],
                        message_id=m["id"],
                        text=_text_of(m),
                        profile_name=names.get(m["from"]),
                        audio_id=audio.get("id"),
                        audio_mime=audio.get("mime_type"),
                    )
                )
    return messages


@dataclass(frozen=True)
class DeliveryStatus:
    """Meta's report on a message Vaani sent: sent, delivered, read, or failed."""

    recipient: str  # wa_id, e.g. 919876543210
    status: str
    errors: list[str]  # "131030 Recipient phone number not in allowed list: ...", when failed


def delivery_statuses(payload: dict) -> list[DeliveryStatus]:
    """Delivery reports in a webhook. Meta accepts a reply first and reports failures
    afterwards, so these are the only place a reply that never arrived shows up."""
    found = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for s in change.get("value", {}).get("statuses", []):
                errors = [
                    " ".join(
                        str(x)
                        for x in (
                            e.get("code"),
                            e.get("title") or e.get("message"),
                            (e.get("error_data") or {}).get("details"),
                        )
                        if x
                    )
                    for e in s.get("errors", [])
                ]
                found.append(
                    DeliveryStatus(str(s.get("recipient_id", "")), str(s.get("status")), errors)
                )
    return found


class WhatsAppClient:
    """Sends through the Graph API. With no access token it only logs (dry run)."""

    def __init__(
        self,
        access_token: str | None,
        graph_version: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.dry_run = not access_token
        self.http = httpx.AsyncClient(
            base_url=f"https://graph.facebook.com/{graph_version}",
            headers={"Authorization": f"Bearer {access_token}"} if access_token else {},
            timeout=10,
            transport=transport,
        )

    async def send_text(self, phone_number_id: str, to: str, body: str) -> None:
        if self.dry_run:
            log.info("[whatsapp dry run] to %s: %s", to[:2] + "******" + to[-4:], body)
            return
        response = await self.http.post(
            f"/{phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body, "preview_url": False},
            },
        )
        response.raise_for_status()

    async def mark_read(self, phone_number_id: str, message_id: str) -> None:
        """Blue ticks plus a typing indicator while the agent thinks. Best effort."""
        if self.dry_run:
            return
        try:
            await self.http.post(
                f"/{phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message_id,
                    "typing_indicator": {"type": "text"},
                },
            )
        except httpx.HTTPError:
            log.debug("mark_read failed", exc_info=True)

    async def download_media(self, media_id: str, max_bytes: int) -> tuple[bytes, str]:
        """Media is fetched in two steps: its metadata gives a short-lived URL,
        which needs the same access token."""
        meta = await self.http.get(f"/{media_id}")
        meta.raise_for_status()
        info = meta.json()
        if int(info.get("file_size") or 0) > max_bytes:
            raise MediaTooLarge(media_id)
        media = await self.http.get(info["url"])
        media.raise_for_status()
        if len(media.content) > max_bytes:
            raise MediaTooLarge(media_id)
        if media.headers.get("content-type", "").startswith("text/html"):
            raise httpx.HTTPError(f"Meta returned a web page instead of media {media_id}")
        return media.content, info.get("mime_type") or media.headers.get("content-type", "")


class WhatsAppAgent:
    """Runs one agent turn per inbound message.

    Messages from the same customer are handled one at a time, so two quick
    messages can't both load the same saved history. The lock is per process;
    running several API instances needs a shared queue (the ARQ milestone).
    """

    def __init__(
        self,
        *,
        settings: AgentSettings,
        llm,
        whatsapp: WhatsAppClient,
        api_for: Callable[[str], VaaniApi],  # business id -> API client
        stt: SarvamSTT | None = None,  # None: voice notes get a "please type" reply
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.whatsapp = whatsapp
        self.api_for = api_for
        self.stt = stt
        self._locks: weakref.WeakValueDictionary[tuple[str, str], asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def _lock(self, business_id: str, wa_id: str) -> asyncio.Lock:
        key = (business_id, wa_id)
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def handle(self, business_id: str, message: InboundMessage) -> None:
        lock = self._lock(business_id, message.wa_id)
        async with lock:
            try:
                reply = await self._turn(business_id, message)
            except Exception:
                log.exception("whatsapp turn failed for message %s", message.message_id)
                reply = ERROR_REPLY
            try:
                await self.whatsapp.send_text(message.phone_number_id, message.wa_id, reply)
            except Exception:
                log.exception("whatsapp send failed for message %s", message.message_id)

    async def _turn(self, business_id: str, message: InboundMessage) -> str:
        await self.whatsapp.mark_read(message.phone_number_id, message.message_id)
        is_voice = (
            message.audio_id is not None and self.stt is not None and not self.whatsapp.dry_run
        )
        if message.text is None and not is_voice:
            return UNSUPPORTED_REPLY

        async with self.api_for(business_id) as api:
            context = await api.context()  # fresh each turn: "now" moves on

            text, voice = message.text, None
            if text is None:
                result = await self._transcribe(message, context)
                if isinstance(result, str):  # a reply to send instead of running the agent
                    return result
                text, voice = result

            conversation = await api.resume_conversation(
                "whatsapp", message.sender_phone, self.settings.whatsapp_idle_minutes
            )
            session = AgentSession(
                api=api,
                llm=self.llm,
                settings=self.settings,
                context=context,
                tool_context=ToolContext(
                    conversation_id=conversation["id"],
                    channel="whatsapp",
                    verified_phone=conversation["customer_phone"],
                ),
                persist_state=True,
            )
            if conversation["agent_state"]:
                session.restore(conversation["agent_state"])
            return await session.reply(text, voice=voice)

    async def _transcribe(
        self, message: InboundMessage, context: dict
    ) -> tuple[str, VoiceNote] | str:
        """The voice note's text, or a reply explaining why it can't be used."""
        s = self.settings
        try:
            audio, mime = await self.whatsapp.download_media(
                message.audio_id, s.voice_note_max_bytes
            )
        except MediaTooLarge:
            return VOICE_TOO_LONG_REPLY

        seconds = ogg_opus_duration(audio) if "ogg" in mime or "opus" in mime else None
        if seconds is not None and seconds > s.voice_note_max_seconds:
            return VOICE_TOO_LONG_REPLY

        started = time.perf_counter()
        try:
            transcript = await self.stt.transcribe(audio, mime, keyterms_for(context))
        except SpeechError:
            log.warning("transcription failed for message %s", message.message_id, exc_info=True)
            return VOICE_NOT_UNDERSTOOD_REPLY
        if not transcript.text:
            return VOICE_NOT_UNDERSTOOD_REPLY

        if seconds is None:
            log.info("unknown length for %s audio; speech cost not counted", mime)
        voice = VoiceNote(
            language_code=transcript.language_code,
            transcription_ms=int((time.perf_counter() - started) * 1000),
            cost_inr=(seconds or 0) / 3600 * s.sarvam_stt_inr_per_hour,
        )
        return transcript.text, voice
