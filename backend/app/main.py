import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import accounts, agent, dashboard, public, tools, voice, whatsapp
from app.config import get_settings, production_problems
from app.errors import VaaniError
from app.https import force_https
from vaani_agent.config import get_agent_settings
from vaani_agent.observability import init_sentry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if get_settings().app_env == "production":
    if problems := production_problems(get_settings(), get_agent_settings().livekit_api_secret):
        raise RuntimeError("Refusing to start in production:\n- " + "\n- ".join(problems))
init_sentry("api")

app = FastAPI(
    title="Vaani API",
    version="0.1.0",
    description="Multilingual AI receptionist: booking tools and conversation logs.",
)
if get_settings().app_env == "production":
    force_https(app)
app.include_router(tools.router)
app.include_router(agent.router)
app.include_router(whatsapp.router)
app.include_router(voice.router)
app.include_router(accounts.router)
app.include_router(dashboard.router)
app.include_router(public.router)


@app.exception_handler(VaaniError)
async def vaani_error(_: Request, exc: VaaniError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, **exc.details},
    )


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"ok": True}
