"""Sliding-window rate limiter middleware for FastAPI.

Uses an in-memory token-bucket per (client_ip, path_prefix) pair.
Falls back gracefully — never blocks if state is corrupted.

Config via env:
    MAIA_RATE_LIMIT_RPM  — requests per minute (default 120)
    MAIA_RATE_LIMIT_AUTH_RPM — auth endpoint rpm (default 20)
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_DEFAULT_RPM = int(os.getenv("MAIA_RATE_LIMIT_RPM", "120"))
_AUTH_RPM = int(os.getenv("MAIA_RATE_LIMIT_AUTH_RPM", "20"))
_WINDOW_S = 60.0

# Path prefixes with tighter limits
_SENSITIVE_PREFIXES = {
    "/api/auth/": _AUTH_RPM,
    "/api/token": _AUTH_RPM,
    "/api/bootstrap": 5,
}


class _TokenBucket:
    __slots__ = ("capacity", "tokens", "last_refill")

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * (self.capacity / _WINDOW_S))
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


# Keyed by (ip, limit_tier)
_buckets: dict[tuple[str, int], _TokenBucket] = defaultdict(lambda: _TokenBucket(_DEFAULT_RPM))


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _limit_for_path(path: str) -> int:
    for prefix, limit in _SENSITIVE_PREFIXES.items():
        if path.startswith(prefix):
            return limit
    return _DEFAULT_RPM


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        ip = _client_ip(request)
        limit = _limit_for_path(request.url.path)
        key = (ip, limit)

        if key not in _buckets:
            _buckets[key] = _TokenBucket(limit)

        bucket = _buckets[key]
        if not bucket.allow():
            logger.warning("Rate limited: %s on %s", ip, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={"Retry-After": str(int(_WINDOW_S))},
            )

        return await call_next(request)
