"""Sign-up, login and logout for the dashboard."""

import re
import secrets
from datetime import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import clock
from app.auth import (
    CurrentUser,
    DashboardDB,
    clear_session,
    hash_password,
    issue_session,
    verify_password,
)
from app.db import system_session
from app.models import Business, User, WorkingHours
from app.ratelimit import RateLimiter
from app.schemas_dashboard import LoginIn, MeOut, PasswordChangeIn, SignupIn
from app.services.dashboard import business_out, user_out

router = APIRouter(prefix="/v1/auth", tags=["auth"])
login_limiter = RateLimiter()

GREETINGS = {
    "te": "Namaskaram! {name} ki swagatam. Meeku ela help cheyagalanu?",
    "hi": "Namaste! {name} mein aapka swagat hai. Main aapki kya madad kar sakti hoon?",
    "en": "Hello! Welcome to {name}. How can I help you?",
}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30].strip("-")
    return slug if len(slug) >= 3 else f"biz-{slug}".strip("-")


@router.post("/signup", status_code=201)
async def signup(body: SignupIn, response: Response) -> MeOut:
    """A new business and its owner account. Starts with Mon-Sat 10:00-19:00 hours,
    which the owner edits in Settings."""
    email = body.email.lower()
    async with system_session() as s:
        if await s.scalar(select(User.id).where(func.lower(User.email) == email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account")
        slug = _slugify(body.business_name)
        if await s.scalar(select(Business.id).where(Business.slug == slug)):
            slug = f"{slug[:34]}-{secrets.token_hex(2)}"
        greeting = GREETINGS.get(body.languages[0], GREETINGS["en"]).format(name=body.business_name)
        business = Business(
            slug=slug,
            name=body.business_name,
            type=body.business_type,
            languages=list(dict.fromkeys(body.languages)),
            greeting=greeting,
        )
        s.add(business)
        await s.flush()
        owner = User(
            business_id=business.id,
            email=email,
            name=body.owner_name,
            role="owner",
            password_hash=hash_password(body.password),
            last_login_at=clock.now(),
        )
        s.add(owner)
        s.add_all(
            WorkingHours(
                business_id=business.id, weekday=d, open_time=time(10), close_time=time(19)
            )
            for d in range(6)
        )
        try:
            await s.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "That email already has an account"
            ) from exc
    issue_session(response, owner)
    return MeOut(user=user_out(owner), business=business_out(business))


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response) -> MeOut:
    client = request.client.host if request.client else "unknown"
    if not login_limiter.allow(f"{client}:{body.email.lower()}", limit=10, window_s=900):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in 15 minutes."
        )
    async with system_session() as s:
        user = await s.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
        if (
            not verify_password(body.password, user.password_hash if user else None)
            or not user.active
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
        user.last_login_at = clock.now()
        business = await s.get(Business, user.business_id)
    issue_session(response, user)
    return MeOut(user=user_out(user), business=business_out(business))


@router.post("/password", status_code=204)
async def change_password(body: PasswordChangeIn, user: CurrentUser, db: DashboardDB) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your current password is wrong")
    user.password_hash = hash_password(body.new_password)
    await db.flush()


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_session(response)
