from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env files.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: str = "development"  # "production" turns on the startup safety checks
    database_url: str = "postgresql+psycopg://vaani_app:vaani_app@localhost:5435/vaani"
    admin_database_url: str = "postgresql+psycopg://vaani_admin:vaani_admin@localhost:5435/vaani"
    agent_api_key: str = "dev-agent-key"

    slot_step_min: int = 15  # slots start on the quarter hour
    booking_lead_min: int = 30  # earliest bookable time is now + this
    availability_search_days: int = 7  # how far ahead to look when a day is full
    # The public booking page: how far ahead patients can book, and per-IP limits
    # (the page needs no login, so these keep bots from filling the calendar).
    public_book_days_ahead: int = 14
    public_bookings_per_ip_per_hour: int = 5
    public_lookups_per_ip_per_hour: int = 300

    # Sign-in attempts per address and email in 15 minutes, against password guessing.
    login_attempts_per_15_min: int = 10
    # Dashboard logins. Set a long random DASHBOARD_JWT_SECRET anywhere public.
    dashboard_jwt_secret: str = "dev-only-dashboard-secret-change-me-0123456789"
    dashboard_session_days: int = 7
    cookie_secure: bool = False  # True when the dashboard is served over HTTPS


DEV_DEFAULTS = {
    "agent_api_key": "dev-agent-key",
    "dashboard_jwt_secret": "dev-only-dashboard-secret-change-me-0123456789",
}


def production_problems(settings: Settings, livekit_api_secret: str) -> list[str]:
    """Settings that are fine on a laptop but unsafe on the internet."""
    problems = []
    for field, default in DEV_DEFAULTS.items():
        value = getattr(settings, field)
        if value == default or len(value) < 32:
            problems.append(f"{field.upper()} must be a random secret of at least 32 characters")
    if not settings.cookie_secure:
        problems.append("COOKIE_SECURE must be true (the dashboard is served over HTTPS)")
    if livekit_api_secret == "secret":
        problems.append("LIVEKIT_API_SECRET is LiveKit's dev secret; use your LiveKit Cloud secret")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
