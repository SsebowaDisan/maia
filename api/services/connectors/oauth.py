"""Generic OAuth2 PKCE flow for any connector.

Responsibility: build authorization URLs, exchange codes, refresh tokens.
Works with any connector whose ConnectorDefinitionSchema has OAuth2AuthConfig.
Credentials stored via the vault after exchange.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from api.schemas.connector_definition import OAuth2AuthConfig
from api.services.connectors import catalog, vault
from api.services.connectors.pkce import derive_code_challenge, generate_code_verifier, get_state_store

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Build authorization URL
# ---------------------------------------------------------------------------

def build_auth_url(
    connector_id: str,
    tenant_id: str,
    redirect_uri: str,
    extra_scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a PKCE authorization URL for a connector.

    Returns {auth_url, state, code_verifier} — the caller should redirect the
    user to auth_url and store state for the callback.
    """
    definition = catalog.get_definition(connector_id)
    if definition is None:
        raise OAuthError("unknown_connector", f"Connector '{connector_id}' not found.")

    if not isinstance(definition.auth, OAuth2AuthConfig):
        raise OAuthError(
            "wrong_auth_type",
            f"Connector '{connector_id}' does not use OAuth2.",
        )

    auth_config: OAuth2AuthConfig = definition.auth
    scopes = list(auth_config.scopes) + list(extra_scopes or [])

    verifier = generate_code_verifier()
    challenge = derive_code_challenge(verifier)

    state = get_state_store().create(
        tenant_id=tenant_id,
        connector_id=connector_id,
        redirect_uri=redirect_uri,
        code_verifier=verifier,
    )

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": _client_id_for(connector_id),
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }

    auth_url = f"{auth_config.authorization_url}?{urllib.parse.urlencode(params)}"
    return {
        "auth_url": auth_url,
        "state": state,
        "connector_id": connector_id,
        "scopes": scopes,
    }


# ---------------------------------------------------------------------------
# Exchange authorization code
# ---------------------------------------------------------------------------

def exchange_code(
    state: str,
    code: str,
) -> dict[str, Any]:
    """Exchange an authorization code for tokens and store via vault.

    Returns {connector_id, tenant_id, scopes, token_type, expires_at}.
    """
    try:
        state_record = get_state_store().consume(state)
    except ValueError as exc:
        raise OAuthError("invalid_state", str(exc)) from exc

    connector_id = state_record.connector_id
    tenant_id = state_record.tenant_id
    redirect_uri = state_record.redirect_uri
    code_verifier = state_record.code_verifier

    definition = catalog.get_definition(connector_id)
    if definition is None or not isinstance(definition.auth, OAuth2AuthConfig):
        raise OAuthError("unknown_connector", f"Connector '{connector_id}' not found.")

    auth_config: OAuth2AuthConfig = definition.auth
    token_response = _post_token(
        token_url=auth_config.token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": _client_id_for(connector_id),
            "client_secret": _client_secret_for(connector_id),
            "code_verifier": code_verifier,
        },
    )

    access_token = str(token_response.get("access_token") or "").strip()
    refresh_token = str(token_response.get("refresh_token") or "").strip()
    expires_in = int(token_response.get("expires_in") or 3600)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    scope_text = str(token_response.get("scope") or "").strip()
    granted_scopes = [s for s in scope_text.split() if s]
    if not granted_scopes:
        granted_scopes = list(auth_config.scopes or [])

    vault.store_oauth_tokens(
        tenant_id=tenant_id,
        connector_id=connector_id,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=expires_at,
        extra={
            "scope": scope_text,
            "granted_scopes": granted_scopes,
        },
    )

    return {
        "connector_id": connector_id,
        "tenant_id": tenant_id,
        "token_type": token_response.get("token_type", "Bearer"),
        "expires_at": expires_at.isoformat(),
        "scopes": " ".join(granted_scopes),
    }


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def refresh_token(tenant_id: str, connector_id: str) -> dict[str, Any]:
    """Use the stored refresh token to get a new access token."""
    creds = vault.get_credential(tenant_id, connector_id)
    stored_refresh = creds.get("refresh_token", "")
    if not stored_refresh:
        raise OAuthError("no_refresh_token", "No refresh token stored for this connector.")

    definition = catalog.get_definition(connector_id)
    if definition is None or not isinstance(definition.auth, OAuth2AuthConfig):
        raise OAuthError("unknown_connector", f"Connector '{connector_id}' not found.")

    auth_config: OAuth2AuthConfig = definition.auth
    token_response = _post_token(
        token_url=auth_config.token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": stored_refresh,
            "client_id": _client_id_for(connector_id),
            "client_secret": _client_secret_for(connector_id),
        },
    )

    access_token = str(token_response.get("access_token") or "").strip()
    new_refresh = str(token_response.get("refresh_token") or stored_refresh).strip()
    expires_in = int(token_response.get("expires_in") or 3600)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    refreshed_scope_text = str(token_response.get("scope") or "").strip()
    granted_scopes = [s for s in refreshed_scope_text.split() if s]
    if not granted_scopes:
        granted_scopes = vault.get_granted_scopes(tenant_id, connector_id)
    if not granted_scopes and isinstance(definition.auth, OAuth2AuthConfig):
        granted_scopes = list(definition.auth.scopes or [])

    vault.store_oauth_tokens(
        tenant_id=tenant_id,
        connector_id=connector_id,
        access_token=access_token,
        refresh_token=new_refresh,
        token_expires_at=expires_at,
        extra={
            "scope": refreshed_scope_text,
            "granted_scopes": granted_scopes,
        },
    )

    return {
        "connector_id": connector_id,
        "tenant_id": tenant_id,
        "expires_at": expires_at.isoformat(),
        "scopes": " ".join(granted_scopes),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _post_token(token_url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        token_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise OAuthError("token_exchange_failed", f"Token endpoint error ({exc.code}): {detail}") from exc
    except Exception as exc:
        raise OAuthError("token_exchange_failed", f"Token request failed: {exc}") from exc


def _client_id_for(connector_id: str) -> str:
    import os
    key = f"MAIA_{connector_id.upper()}_CLIENT_ID"
    return os.getenv(key, "")


def _client_secret_for(connector_id: str) -> str:
    import os
    key = f"MAIA_{connector_id.upper()}_CLIENT_SECRET"
    return os.getenv(key, "")
