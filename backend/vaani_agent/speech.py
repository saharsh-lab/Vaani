"""Speech-to-text with Sarvam (https://docs.sarvam.ai), for WhatsApp voice notes.

The synchronous REST endpoint takes up to 30 seconds of audio; longer files need
Sarvam's batch API, which is too slow for a chat reply.
"""

import json
import struct
from dataclasses import dataclass

import httpx

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
MAX_KEYTERMS = 50  # Sarvam's limit, saaras:v4 only
MAX_KEYTERM_CHARS = 64

_EXTENSIONS = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
}


class SpeechError(Exception):
    """Sarvam couldn't transcribe the audio (bad format, too long, or an outage)."""


@dataclass(frozen=True)
class Transcript:
    text: str
    language_code: str | None  # BCP-47, e.g. te-IN; None if Sarvam couldn't tell


def ogg_opus_duration(data: bytes) -> float | None:
    """Length in seconds of an Ogg Opus file (WhatsApp voice notes), from its headers.

    Opus counts time in 48 kHz samples: the last page's granule position, minus
    the encoder's pre-skip from the OpusHead header, is the length.
    """
    head = data.find(b"OpusHead")
    last_page = _last_ogg_page(data)
    if head < 0 or last_page is None or len(data) < head + 12:
        return None
    (pre_skip,) = struct.unpack_from("<H", data, head + 10)
    (granule,) = struct.unpack_from("<q", data, last_page + 6)
    if granule < 0:
        return None
    return max(granule - pre_skip, 0) / 48_000


def _last_ogg_page(data: bytes) -> int | None:
    """Offset of the final Ogg page: an "OggS" header whose page ends exactly at
    the end of the file (the same four bytes can occur inside audio data)."""
    pos = len(data)
    while (pos := data.rfind(b"OggS", 0, pos)) >= 0:
        if pos + 27 <= len(data) and data[pos + 4] == 0:  # header size; version 0
            segments = data[pos + 26]
            table_end = pos + 27 + segments
            if table_end <= len(data) and table_end + sum(data[pos + 27 : table_end]) == len(data):
                return pos
    return None


def keyterms_for(context: dict) -> list[str]:
    """Names the recogniser should expect: the business, its services and staff."""
    terms = [context["name"], *(s["name"] for s in context["services"]), *context["staff"]]
    unique = dict.fromkeys(t[:MAX_KEYTERM_CHARS] for t in terms if t)
    return list(unique)[:MAX_KEYTERMS]


class SarvamSTT:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "saaras:v4",
        mode: str = "transcribe",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.mode = mode
        self.http = httpx.AsyncClient(
            headers={"api-subscription-key": api_key}, timeout=30, transport=transport
        )

    async def transcribe(
        self, audio: bytes, mime_type: str, keyterms: list[str] | None = None
    ) -> Transcript:
        content_type = mime_type.split(";")[0].strip().lower()
        filename = "voice-note" + _EXTENSIONS.get(content_type, "")
        form = {"model": self.model, "mode": self.mode}
        if keyterms and self.model.startswith("saaras:v4"):
            form["keyterms"] = json.dumps(keyterms[:MAX_KEYTERMS], ensure_ascii=False)
        try:
            response = await self.http.post(
                SARVAM_STT_URL, data=form, files={"file": (filename, audio, content_type)}
            )
        except httpx.HTTPError as exc:
            raise SpeechError(f"Sarvam unreachable: {exc}") from exc
        if response.is_error:
            raise SpeechError(f"Sarvam returned {response.status_code}: {response.text[:300]}")
        body = response.json()
        return Transcript(
            text=(body.get("transcript") or "").strip(),
            language_code=body.get("language_code"),
        )
