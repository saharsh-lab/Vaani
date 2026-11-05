"""HTTPS only, in production.

The host's proxy (Railway, Render, ...) terminates TLS and forwards each public
request over plain HTTP with X-Forwarded-Proto saying how the visitor connected.
A visitor who came over plain HTTP is redirected, and HTTPS responses tell
browsers to use HTTPS from then on (HSTS).

Only that header decides. Requests without it never passed through the public
proxy: the platform's health checks, and the API calling itself in-process (the
WhatsApp agent uses the tools at http://vaani.internal). Redirecting those
broke WhatsApp replies.
"""

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

HSTS = "max-age=63072000; includeSubDomains"  # two years


def force_https(app: FastAPI) -> None:
    @app.middleware("http")
    async def https_only(request: Request, call_next):
        if request.headers.get("x-forwarded-proto") == "http":
            # 308 keeps the method and body, so a POST is retried as a POST.
            return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)
        response = await call_next(request)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = HSTS
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
