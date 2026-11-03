from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Real environment variables win over .env files.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://vaani_app:vaani_app@localhost:5435/vaani"
    admin_database_url: str = "postgresql+psycopg://vaani_admin:vaani_admin@localhost:5435/vaani"
    agent_api_key: str = "dev-agent-key"

    slot_step_min: int = 15  # slots start on the quarter hour
    booking_lead_min: int = 30  # earliest bookable time is now + this
    availability_search_days: int = 7  # how far ahead to look when a day is full

    # Dashboard logins. Set a long random DASHBOARD_JWT_SECRET anywhere public.
    dashboard_jwt_secret: str = "dev-only-dashboard-secret-change-me-0123456789"
    dashboard_session_days: int = 7
    cookie_secure: bool = False  # True when the dashboard is served over HTTPS


@lru_cache
def get_settings() -> Settings:
    return Settings()
