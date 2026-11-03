"""A Gemini client wrapper for eval runs: caps requests per minute and
concurrency, and retries rate-limit and overload errors with backoff, so a full
run fits inside free-tier limits."""

import asyncio
import contextvars
import logging
import time
from types import SimpleNamespace

from google.genai import errors

log = logging.getLogger("vaani.evals")

RETRYABLE = {429, 500, 503}


def is_capacity_error(exc: BaseException) -> bool:
    """Quota or overload from Gemini: not the agent's fault, so not scored."""
    return isinstance(exc, errors.APIError) and exc.code in RETRYABLE


def eval_client(api_key: str):
    """A Gemini client with the SDK's own retries off: ThrottledLLM retries instead,
    so it can tell waiting apart from model time."""
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
    )


# Seconds spent waiting (pacing, queueing, rate-limit backoff) in the current
# task, so turn latency can exclude time that only exists because of the
# eval's own rate limiting.
WAITED: contextvars.ContextVar[list[float] | None] = contextvars.ContextVar(
    "vaani_eval_waited", default=None
)


class ThrottledLLM:
    def __init__(self, client, *, rpm: int, concurrency: int, retries: int = 6) -> None:
        self.client = client
        self.aio = SimpleNamespace(models=self)  # same shape as genai.Client
        self.interval = 60.0 / rpm
        self.semaphore = asyncio.Semaphore(concurrency)
        self.retries = retries
        self._next_slot = 0.0
        self._lock = asyncio.Lock()
        self.calls = 0

    async def _pace(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)

    async def generate_content(self, **kwargs):
        started = time.monotonic()
        for attempt in range(self.retries + 1):
            async with self.semaphore:
                await self._pace()
                call_started = time.monotonic()
                try:
                    self.calls += 1
                    result = await self.client.aio.models.generate_content(**kwargs)
                    if (waited := WAITED.get()) is not None:
                        waited[0] += call_started - started
                    return result
                except errors.APIError as exc:
                    if exc.code not in RETRYABLE or attempt == self.retries:
                        raise
                    delay = min(60.0, 2.0 * 2**attempt)
                    log.warning("Gemini %s; retrying in %.0fs", exc.code, delay)
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")
