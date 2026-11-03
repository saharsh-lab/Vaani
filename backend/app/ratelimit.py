"""A small in-memory rate limiter for public endpoints (voice calls, logins)."""

import time
from collections import defaultdict, deque


class RateLimiter:
    """At most `limit` calls per key in a sliding hour. In memory, per process;
    behind a proxy, key on the forwarded client IP instead."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_s: float = 3600) -> bool:
        now = time.monotonic()
        hits = self.hits[key]
        while hits and now - hits[0] > window_s:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True
