"""Dashboard logins for business owners and staff: email + password.

Sessions are signed JWTs in an httpOnly cookie (or an Authorization: Bearer header
for API clients). Every dashboard request runs in the session's tenant, so row-level
security limits it to that business. The user's role is re-read from the database
on each request, so removing someone or changing their role applies immediately.

To move to Supabase Auth later, replace `read_session` with Supabase JWT
verification and map the Supabase user to a row in `users`.
"""

import base64
import hashlib
import hmac
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import tenant_session
from app.models import Business, User

SESSION_COOKIE = "vaani_session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        # Unknown account: do the same work anyway, so timing doesn't reveal it.
        hashlib.scrypt(password.encode(), salt=bytes(16), **_SCRYPT)
        return False
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **_SCRYPT)
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def issue_session(response: Response, user: User) -> None:
    settings = get_settings()
    now = datetime.now(UTC)  # real time, not the business clock
    expires = now + timedelta(days=settings.dashboard_session_days)
    token = jwt.encode(
        {"sub": str(user.id), "bid": str(user.business_id), "iat": now, "exp": expires},
        settings.dashboard_jwt_secret,
        algorithm="HS256",
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",  # not sent on cross-site POSTs, which blocks CSRF
        secure=settings.cookie_secure,
        max_age=settings.dashboard_session_days * 86400,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def read_session(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    header = request.headers.get("authorization", "")
    if not token and header.lower().startswith("bearer "):
        token = header[7:]
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        return jwt.decode(token, get_settings().dashboard_jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired; sign in again") from exc


Claims = Annotated[dict, Depends(read_session)]


async def dashboard_db(claims: Claims) -> AsyncIterator[AsyncSession]:
    async with tenant_session(uuid.UUID(claims["bid"])) as session:
        yield session


DashboardDB = Annotated[AsyncSession, Depends(dashboard_db)]


async def current_user(claims: Claims, db: DashboardDB) -> User:
    user = await db.get(User, uuid.UUID(claims["sub"]))  # row-level security: own business only
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not active")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_owner(user: CurrentUser) -> User:
    if user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the business owner can do this")
    return user


Owner = Annotated[User, Depends(require_owner)]


async def viewer_business(db: DashboardDB, user: CurrentUser) -> Business:
    business = await db.get(Business, user.business_id)
    if business is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Business not found")
    return business


ViewerBusiness = Annotated[Business, Depends(viewer_business)]
