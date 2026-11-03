"""Sarvam speech-to-text client and voice-note helpers."""

import json

import httpx
import pytest

from tests.fakes import ogg_opus
from vaani_agent.speech import (
    SARVAM_STT_URL,
    SarvamSTT,
    SpeechError,
    keyterms_for,
    ogg_opus_duration,
)


@pytest.mark.parametrize("seconds", [0.5, 8, 29.9, 45])
def test_reads_voice_note_length_from_ogg_headers(seconds):
    assert ogg_opus_duration(ogg_opus(seconds)) == pytest.approx(seconds, abs=0.001)


@pytest.mark.parametrize("data", [b"", b"ID3 not an ogg file", ogg_opus(5)[:30]])
def test_unknown_length_for_non_ogg_or_truncated_audio(data):
    assert ogg_opus_duration(data) is None


def test_keyterms_are_business_service_and_staff_names():
    context = {
        "name": "Sri Dental Clinic",
        "services": [{"name": "RCT consultation"}, {"name": "x" * 80}],
        "staff": ["Dr. Lakshmi Reddy", "Dr. Lakshmi Reddy"],
    }
    assert keyterms_for(context) == [
        "Sri Dental Clinic",
        "RCT consultation",
        "x" * 64,
        "Dr. Lakshmi Reddy",
    ]


def sarvam(handler) -> SarvamSTT:
    return SarvamSTT("sk-test", transport=httpx.MockTransport(handler))


async def test_transcribe_sends_audio_model_and_keyterms():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["api-subscription-key"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "request_id": "r1",
                "transcript": " repu evening slot undaa ",
                "language_code": "te-IN",
            },
        )

    transcript = await sarvam(handler).transcribe(
        b"OggS-audio", "audio/ogg; codecs=opus", ["RCT consultation", "డాక్టర్"]
    )
    assert transcript.text == "repu evening slot undaa"
    assert transcript.language_code == "te-IN"
    assert seen["url"] == SARVAM_STT_URL and seen["key"] == "sk-test"
    body = seen["body"]
    assert b'name="model"\r\n\r\nsaaras:v4' in body
    assert b'name="mode"\r\n\r\ntranscribe' in body
    assert json.dumps(["RCT consultation", "డాక్టర్"], ensure_ascii=False).encode() in body
    assert b'filename="voice-note.ogg"' in body and b"Content-Type: audio/ogg" in body


async def test_keyterms_only_sent_to_models_that_support_them():
    bodies = []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(200, json={"transcript": "hi", "language_code": "en-IN"})

    stt = SarvamSTT("sk", model="saaras:v3", transport=httpx.MockTransport(handler))
    await stt.transcribe(b"audio", "audio/ogg", ["RCT consultation"])
    assert b"keyterms" not in bodies[0]


async def test_api_errors_become_speech_errors():
    def rejects(request):
        return httpx.Response(422, json={"error": {"message": "Audio longer than 30 seconds"}})

    with pytest.raises(SpeechError, match="422"):
        await sarvam(rejects).transcribe(b"audio", "audio/ogg")

    def unreachable(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(SpeechError, match="unreachable"):
        await sarvam(unreachable).transcribe(b"audio", "audio/ogg")


def test_ignores_ogg_magic_bytes_inside_audio_data():
    # Hide "OggS" and a huge fake granule in the final page's audio payload, where
    # a plain backwards search would find it before the real page header.
    import struct

    data = ogg_opus(10)
    fake = b"OggS\x00\x00" + struct.pack("<q", 10**12)
    at = data.rfind(b"\x00" * 30)
    assert at > data.rfind(b"OggS")  # inside the last page's payload
    tricky = data[:at] + fake + data[at + len(fake) :]
    assert ogg_opus_duration(tricky) == pytest.approx(10, abs=0.001)
