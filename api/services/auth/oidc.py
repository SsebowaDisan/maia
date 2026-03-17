"""OIDC discovery + token exchange service.

Reads provider configuration from environment variables and caches the
OpenID Connect discovery document in memory with a 1-hour TTL.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

from jose import jwt

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

OIDC_ISSUER_URL = os.getenv("MAIA_OIDC_ISSUER_URL", "")
OIDC_CLIENT_ID = os.getenv("MAIA_OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.getenv("MAIA_OIDC_CLIENT_SECRET", "")
OIDC_REDIRECT_URI = os.getenv("MAIA_OIDC_REDIRECT_URI", "")

# ── Discovery cache ──────────────────────────────────────────────────────────

_discovery_cache: dict[str, Any] | None = None
_discovery_fetched_at: float = 0.0
_DISCOVERY_TTL = 3600  # 1 hour

_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0


def is_oidc_configured() -> bool:
    """Return True when all required OIDC env vars are set."""
    return all([OIDC_ISSUER_URL, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_REDIRECT_URI])


def _http_get_json(url: str) -> dict[str, Any]:
    """Fetch JSON from *url* using stdlib only."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    """POST form-encoded *data* to *url* and return JSON response."""
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Need urllib.parse for urlencode / quote
import urllib.parse  # noqa: E402


def _get_discovery() -> dict[str, Any]:
    """Return the OIDC discovery document, caching for 1 hour."""
    global _discovery_cache, _discovery_fetched_at
    now = time.monotonic()
    if _discovery_cache is not None and (now - _discovery_fetched_at) < _DISCOVERY_TTL:
        return _discovery_cache

    url = OIDC_ISSUER_URL.rstrip("/") + "/.well-known/openid-configuration"
    logger.info("Fetching OIDC discovery from %s", url)
    _discovery_cache = _http_get_json(url)
    _discovery_fetched_at = now
    return _discovery_cache


def _get_jwks() -> dict[str, Any]:
    """Fetch the JWKS key set from the provider (cached 1 hour)."""
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache is not None and (now - _jwks_fetched_at) < _DISCOVERY_TTL:
        return _jwks_cache

    discovery = _get_discovery()
    jwks_uri = discovery["jwks_uri"]
    logger.info("Fetching JWKS from %s", jwks_uri)
    _jwks_cache = _http_get_json(jwks_uri)
    _jwks_fetched_at = now
    return _jwks_cache


# ── Public API ───────────────────────────────────────────────────────────────

def get_authorization_url(state: str, nonce: str) -> str:
    """Build the OIDC authorize URL from the discovery document."""
    discovery = _get_discovery()
    auth_endpoint = discovery["authorization_endpoint"]
    params = {
        "response_type": "code",
        "client_id": OIDC_CLIENT_ID,
        "redirect_uri": OIDC_REDIRECT_URI,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    return f"{auth_endpoint}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, state: str, nonce: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens and return user claims.

    Returns ``{"sub": ..., "email": ..., "name": ..., "tid": ...}``.
    Raises ``ValueError`` on any validation failure.
    """
    discovery = _get_discovery()
    token_endpoint = discovery["token_endpoint"]

    token_resp = _http_post_form(token_endpoint, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OIDC_REDIRECT_URI,
        "client_id": OIDC_CLIENT_ID,
        "client_secret": OIDC_CLIENT_SECRET,
    })

    id_token_raw = token_resp.get("id_token")
    if not id_token_raw:
        raise ValueError("No id_token in token response")

    # Decode and verify the ID token using JWKS
    jwks = _get_jwks()
    try:
        claims = jwt.decode(
            id_token_raw,
            jwks,
            algorithms=["RS256", "RS384", "RS512", "ES256", "ES384"],
            audience=OIDC_CLIENT_ID,
            issuer=OIDC_ISSUER_URL.rstrip("/"),
            options={"verify_at_hash": False},
        )
    except Exception as exc:
        logger.error("ID token verification failed: %s", exc)
        raise ValueError(f"ID token verification failed: {exc}") from exc

    # Validate nonce to prevent replay
    if claims.get("nonce") != nonce:
        raise ValueError("Nonce mismatch — possible replay attack")

    email = claims.get("email") or claims.get("preferred_username", "")
    name = claims.get("name") or claims.get("preferred_username", "")
    tid = claims.get("tid")  # Azure AD tenant claim; None for other IdPs

    if not email:
        raise ValueError("ID token does not contain an email claim")

    return {"sub": claims["sub"], "email": email, "name": name, "tid": tid}
