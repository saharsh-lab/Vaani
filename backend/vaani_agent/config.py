from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The name the voice worker registers under; the API dispatches calls to it.
VOICE_AGENT_NAME = "vaani-voice"


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    api_base_url: str = "http://localhost:8000"
    agent_api_key: str = "dev-agent-key"
    gemini_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    gemini_model: str = "gemini-3.5-flash-lite"

    # For cost per conversation: Gemini 3.5 Flash-Lite as listed by price trackers in
    # Nov 2026. Confirm on ai.google.dev/gemini-api/docs/pricing before quoting numbers.
    llm_input_usd_per_million: float = 0.30
    llm_output_usd_per_million: float = 2.50
    usd_to_inr: float = 88.0

    # WhatsApp Cloud API (Meta app dashboard). Without an access token, replies
    # are logged instead of sent, which is enough to try the webhook locally.
    whatsapp_verify_token: str | None = None  # any string; also entered in Meta's webhook form
    whatsapp_app_secret: str | None = None  # App settings > Basic; signs every webhook
    whatsapp_access_token: str | None = None
    whatsapp_graph_version: str = "v23.0"
    whatsapp_idle_minutes: int = 30  # a gap longer than this starts a new conversation

    # Sarvam speech-to-text, for WhatsApp voice notes. Without a key, voice notes
    # get a "please type" reply.
    sarvam_api_key: str | None = None
    sarvam_stt_model: str = "saaras:v4"
    sarvam_stt_mode: str = "transcribe"  # see Sarvam's docs for codemix / translit
    sarvam_stt_inr_per_hour: float = 29.40  # from the project spec; check current pricing
    voice_note_max_seconds: int = 30  # Sarvam's synchronous API limit
    voice_note_max_bytes: int = 2_000_000

    # Real-time voice over LiveKit. `docker compose up -d livekit` runs a local dev
    # server with these defaults; LiveKit Cloud gives you your own url, key and secret.
    livekit_url: str = "ws://localhost:7880"
    livekit_public_url: str | None = None  # what browsers connect to, if not livekit_url
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    sarvam_tts_model: str = "bulbul:v4-flash"
    # Bulbul v4 Flash voices are per language, so the voice switches with the caller.
    # Override with JSON, e.g. SARVAM_TTS_SPEAKERS='{"te-IN": "kavitha_te_conversation", ...}'.
    sarvam_tts_speakers: dict[str, str] = {
        "te-IN": "pooja_te_conversation",
        "hi-IN": "ishita_enhi_customer",
        "en-IN": "ishita_en_customer",
    }
    sarvam_tts_inr_per_10k_chars: float = 10.0  # from the project spec; check current pricing
    voice_max_call_seconds: int = 300  # caps cost per call, and abuse of the public demo
    voice_calls_per_ip_per_hour: int = 20
    # Warm worker processes waiting for calls; each holds the VAD model (~150 MB).
    voice_idle_processes: int = 2


@lru_cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
