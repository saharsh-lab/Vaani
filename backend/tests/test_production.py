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


# HTTPS only ---------------------------------------------------------------------


def https_app():
    from fastapi import FastAPI

    from app.https import force_https

    app = FastAPI()
    force_https(app)

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/v1/things")
    async def things():
        return {"made": True}

    return app


async def test_plain_http_is_redirected_to_https():
    import httpx

    transport = httpx.ASGITransport(app=https_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://api.example.com") as c:
        # What Railway's proxy forwards when a visitor connected over plain HTTP.
        r = await c.post("/v1/things?x=1", headers={"x-forwarded-proto": "http"})
    assert r.status_code == 308  # keeps the POST
    assert r.headers["location"] == "https://api.example.com/v1/things?x=1"


async def test_https_responses_tell_browsers_to_stay_on_https():
    import httpx

    transport = httpx.ASGITransport(app=https_app())
    async with httpx.AsyncClient(transport=transport, base_url="https://api.example.com") as c:
        r = await c.post("/v1/things")
    assert r.status_code == 200
    assert r.headers["strict-transport-security"].startswith("max-age=63072000")
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_the_api_can_call_itself_in_process():
    # The WhatsApp agent calls the tools at http://vaani.internal, with no proxy in between.
    import httpx

    transport = httpx.ASGITransport(app=https_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://vaani.internal") as c:
        r = await c.post("/v1/things")
    assert r.status_code == 200 and r.json() == {"made": True}


async def test_health_checks_still_work_over_plain_http():
    import httpx

    transport = httpx.ASGITransport(app=https_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://10.0.0.5:8000") as c:
        r = await c.get("/health")
    assert r.status_code == 200 and "strict-transport-security" not in r.headers
