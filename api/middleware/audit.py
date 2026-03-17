"""Centralized audit-logging middleware for FastAPI.

Logs every request/response cycle with timing, status code, and caller identity.
Sensitive auth headers are redacted. Body content is never logged.

Config via env:
    MAIA_AUDIT_LOG_ENABLED — set to "0" to disable (default "1")
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_ENABLED = os.getenv("MAIA_AUDIT_LOG_ENABLED", "1") != "0"
_REDACTED_HEADERS = {"authorization", "cookie", "x-api-key"}

logger = logging.getLogger("maia.audit")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _safe_user_id(request: Request) -> str:
    """Extract user_id from request state if auth middleware set it."""
    return getattr(request.state, "user_id", "-")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not _ENABLED:
            return await call_next(request)

        start = time.perf_counter()
        ip = _client_ip(request)
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            logger.error(
                "AUDIT ip=%s method=%s path=%s status=500 ms=%.1f user=%s error=unhandled_exception",
                ip, method, path, elapsed_ms, _safe_user_id(request),
            )
            raise

        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        log_fn = logger.warning if response.status_code >= 400 else logger.info
        log_fn(
            "AUDIT ip=%s method=%s path=%s status=%d ms=%.1f user=%s",
            ip, method, path, response.status_code, elapsed_ms, _safe_user_id(request),
        )
        return response
