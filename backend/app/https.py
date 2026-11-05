"""HTTPS only, in production.

The host's proxy (Railway, Render, ...) terminates TLS and forwards the request
over plain HTTP with X-Forwarded-Proto; uvicorn's --proxy-headers turns that
into the request's scheme. A request that arrived as plain HTTP is redirected,
and every response tells browsers to use HTTPS from then on (HSTS).
"""

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

# Platform health checks call the container directly, over plain HTTP.
EXEMPT_PATHS = {"/health"}
HSTS = "max-age=63072000; includeSubDomains"  # two years


def force_https(app: FastAPI) -> None:
    @app.middleware("http")
    async def https_only(request: Request, call_next):
        if request.url.scheme == "http" and request.url.path not in EXEMPT_PATHS:
            # 308 keeps the method and body, so a POST is retried as a POST.
            return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)
        response = await call_next(request)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = HSTS
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
