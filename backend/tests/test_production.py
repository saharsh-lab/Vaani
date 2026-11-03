"""The API refuses to start on the internet with laptop defaults."""

import secrets

from app.config import Settings, production_problems


def test_development_defaults_are_refused():
    problems = production_problems(Settings(_env_file=None), livekit_api_secret="secret")
    assert any("AGENT_API_KEY" in p for p in problems)
    assert any("DASHBOARD_JWT_SECRET" in p for p in problems)
    assert any("COOKIE_SECURE" in p for p in problems)
    assert any("LIVEKIT_API_SECRET" in p for p in problems)


def test_real_secrets_pass():
    settings = Settings(
        _env_file=None,
        agent_api_key=secrets.token_urlsafe(32),
        dashboard_jwt_secret=secrets.token_urlsafe(48),
        cookie_secure=True,
    )
    assert production_problems(settings, livekit_api_secret=secrets.token_urlsafe(32)) == []


def test_short_secrets_are_refused():
    settings = Settings(
        _env_file=None, agent_api_key="short", dashboard_jwt_secret="x" * 40, cookie_secure=True
    )
    assert production_problems(settings, livekit_api_secret="a-real-livekit-secret") == [
        "AGENT_API_KEY must be a random secret of at least 32 characters"
    ]
