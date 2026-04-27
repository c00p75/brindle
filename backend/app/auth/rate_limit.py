"""Simple in-memory sliding-window rate limiter.

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


# 10 login attempts per 60 s per IP
login_limiter = RateLimiter(max_requests=10, window_seconds=60)

# 5 password reset requests per 10 min per IP
forgot_password_limiter = RateLimiter(max_requests=5, window_seconds=600)

# 10 TOTP attempts per 5 min per IP (generous for legitimate users, blocks bots)
totp_limiter = RateLimiter(max_requests=10, window_seconds=300)
