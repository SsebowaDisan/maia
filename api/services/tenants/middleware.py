"""TenantContextMiddleware — enrich request.state with tenant context.

Attaches ``request.state.tenant_id`` and ``request.state.user_id`` early
in the request lifecycle so that downstream middleware (audit logging,
rate limiting, etc.) can rely on them without re-parsing auth headers.

This is *best-effort*: unauthenticated requests (health checks, public
endpoints) pass through without error — the state attributes are simply
left unset.
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from api.services.tenants.resolver import resolve_tenant_id

log = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Populate ``request.state.{user_id, tenant_id}`` for every request."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Defaults — may be overwritten below
        request.state.user_id = None
        request.state.tenant_id = None

        try:
            user = await self._try_resolve_user(request)
            if user is not None:
                request.state.user_id = user.id
                request.state.tenant_id = resolve_tenant_id(user)
        except Exception:  # noqa: BLE001
            # Best-effort: don't block the request if resolution fails.
            log.debug("TenantContextMiddleware: could not resolve tenant", exc_info=True)

        return await call_next(request)

    # ------------------------------------------------------------------

    @staticmethod
    async def _try_resolve_user(request: Request):
        """Attempt to load the User from the Authorization header.

        Returns the User or None.  Imports are deferred to avoid circular
        dependencies at module level.
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None

        token = auth_header[7:].strip()
        if not token:
            return None

        # API key path
        if token.startswith("mk_"):
            from api.services.auth.api_keys import verify_api_key
            from api.services.auth.store import get_user

            key_record = verify_api_key(token)
            if key_record is None:
                return None
            return get_user(key_record.user_id)

        # JWT path
        from api.services.auth.store import get_user
        from api.services.auth.tokens import TokenError, decode_access_token

        try:
            payload = decode_access_token(token)
        except TokenError:
            return None

        uid = payload.get("sub")
        if not uid:
            return None
        return get_user(str(uid))
