"""The one place the app reads the current time, so tests can freeze it."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
