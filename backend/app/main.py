import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import accounts, agent, dashboard, tools, voice, whatsapp
from app.errors import VaaniError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Vaani API",
    version="0.1.0",
    description="Multilingual AI receptionist: booking tools and conversation logs.",
)
app.include_router(tools.router)
app.include_router(agent.router)
app.include_router(whatsapp.router)
app.include_router(voice.router)
app.include_router(accounts.router)
app.include_router(dashboard.router)


@app.exception_handler(VaaniError)
async def vaani_error(_: Request, exc: VaaniError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, **exc.details},
    )


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"ok": True}
