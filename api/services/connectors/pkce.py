"""PKCE helpers — code verifier/challenge generation and state token management.

Responsibility: stateless PKCE crypto primitives + in-memory state token store.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from threading import Lock


# ---------------------------------------------------------------------------
# PKCE primitives
# ---------------------------------------------------------------------------

def generate_code_verifier() -> str:
    """Generate a cryptographically random PKCE code verifier (43-128 chars)."""
    return base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()


def derive_code_challenge(verifier: str) -> str:
    """Derive the S256 code challenge from a code verifier."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# ---------------------------------------------------------------------------
# State token store (CSRF protection)
# ---------------------------------------------------------------------------

_STATE_TTL_SECONDS = 600  # 10 minutes


class _StateRecord:
    __slots__ = ("tenant_id", "connector_id", "redirect_uri", "code_verifier", "extra", "expires_at")

    def __init__(
        self,
        tenant_id: str,
        connector_id: str,
        redirect_uri: str,
        code_verifier: str,
        extra: dict,
    ) -> None:
        self.tenant_id = tenant_id
        self.connector_id = connector_id
        self.redirect_uri = redirect_uri
        self.code_verifier = code_verifier
        self.extra = extra
        self.expires_at = time.monotonic() + _STATE_TTL_SECONDS


class StateStore:
    """In-memory store for OAuth2 state tokens (single process, no persistence needed)."""

    def __init__(self) -> None:
        self._store: dict[str, _StateRecord] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        tenant_id: str,
        connector_id: str,
        redirect_uri: str,
        code_verifier: str,
        extra: dict | None = None,
    ) -> str:
        """Create and store a new state token. Returns the state string."""
        state = secrets.token_urlsafe(32)
        record = _StateRecord(
            tenant_id=tenant_id,
            connector_id=connector_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            extra=extra or {},
        )
        with self._lock:
            self._purge_expired()
            self._store[state] = record
        return state

    def consume(self, state: str) -> _StateRecord:
        """Consume and return the state record. Raises ValueError if invalid/expired."""
        with self._lock:
            record = self._store.pop(state, None)
        if record is None:
            raise ValueError("OAuth state token not found or already used.")
        if time.monotonic() > record.expires_at:
            raise ValueError("OAuth state token has expired.")
        return record

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for key in expired:
            del self._store[key]


_state_store: StateStore | None = None


def get_state_store() -> StateStore:
    global _state_store
    if _state_store is None:
        _state_store = StateStore()
    return _state_store
