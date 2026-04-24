"""Simple in-memory sliding-window rate limiter.

Used on the login endpoint to prevent brute-force attacks.
Single-process only — if you scale horizontally, back this with Redis.
"""
from __future__ import annotations

from app.core.time import now_epoch_ms


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self._max = max_requests
        self._window_ms = window_seconds * 1000
        self._buckets: dict[str, list[int]] = {}

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within the rate limit, False if blocked."""
        now = now_epoch_ms()
        cutoff = now - self._window_ms
        timestamps = [t for t in self._buckets.get(key, []) if t > cutoff]
        if len(timestamps) >= self._max:
            self._buckets[key] = timestamps
            return False
        timestamps.append(now)
        self._buckets[key] = timestamps
        return True

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)


# Process-level singleton: 10 attempts per 60 s per IP.
login_limiter = RateLimiter(max_requests=10, window_seconds=60)
