from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from api.services.google.errors import (
    GoogleOAuthError,
    GoogleServiceError,
    GoogleTokenError,
)
from api.services.google.oauth_scopes import (
    enabled_service_ids_from_scopes,
    enabled_tool_ids_from_scopes,
)
from api.services.google.session import GoogleAuthSession  # noqa: F401
from api.services.google.store import GoogleTokenRecord, OAuthStateRecord, get_google_token_store, get_oauth_state_store
from .oauth_auth_config_helpers import (
    OAuthStartResult,
    iso_now,
    load_default_scopes,
    oauth_configuration_status_impl,
    oauth_env,
    oauth_store_values,
    parse_token_scopes,
    queue_google_oauth_setup_request_impl,
    resolve_google_oauth_config_impl,
    resolve_google_redirect_uri_impl,
    safe_http_error_message,
    save_google_oauth_configuration_impl,
    save_oauth_store_values,
    saved_oauth_services_for_user,
    tenant_id_for_user,
    normalize_oauth_setup_requests,
)

DEFAULT_REDIRECT_URI = "http://localhost:8000/api/agent/oauth/google/callback"
DEFAULT_FRONTEND_SUCCESS_URL = "http://localhost:5173/settings?oauth=success"
DEFAULT_FRONTEND_ERROR_URL = "http://localhost:5173/settings?oauth=error"
DEFAULT_SCOPES = load_default_scopes()
GOOGLE_OAUTH_CONFIG_CONNECTOR_ID = "google_oauth"
GOOGLE_OAUTH_KEYS = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
)
OAUTH_OWNER_USER_ID_KEY = "MAIA_OAUTH_OWNER_USER_ID"
OAUTH_OWNER_SET_AT_KEY = "MAIA_OAUTH_OWNER_SET_AT"
OAUTH_SETUP_REQUESTS_KEY = "MAIA_OAUTH_SETUP_REQUESTS"


def _iso_now() -> str: return iso_now()
def _oauth_env(name: str) -> str: return oauth_env(name)
def _load_default_scopes() -> list[str]: return load_default_scopes()
def _tenant_id_for_user(user_id: str) -> str: return tenant_id_for_user(user_id)
def _saved_oauth_services_for_user(user_id: str | None) -> list[str]: return saved_oauth_services_for_user(user_id)
def _oauth_store_values(
    user_id: str | None = None,
    *,
    include_metadata: bool = False,
) -> dict[str, Any]:
    return oauth_store_values(user_id, include_metadata=include_metadata, tenant_id_for_user_fn=_tenant_id_for_user, oauth_keys=GOOGLE_OAUTH_KEYS, owner_user_id_key=OAUTH_OWNER_USER_ID_KEY, owner_set_at_key=OAUTH_OWNER_SET_AT_KEY, setup_requests_key=OAUTH_SETUP_REQUESTS_KEY, connector_id=GOOGLE_OAUTH_CONFIG_CONNECTOR_ID)
def resolve_google_oauth_config(user_id: str | None = None) -> dict[str, str]:
    return resolve_google_oauth_config_impl(user_id=user_id, oauth_keys=GOOGLE_OAUTH_KEYS, oauth_env_fn=_oauth_env, oauth_store_values_fn=_oauth_store_values, default_redirect_uri=DEFAULT_REDIRECT_URI)
def resolve_google_redirect_uri(override: str | None = None, *, user_id: str | None = None) -> str:
    return resolve_google_redirect_uri_impl(override=override, user_id=user_id, resolve_google_oauth_config_fn=resolve_google_oauth_config)
def _normalize_oauth_setup_requests(raw: Any) -> list[dict[str, str]]: return normalize_oauth_setup_requests(raw, iso_now_fn=_iso_now)
def _save_oauth_store_values(user_id: str, values: dict[str, Any]) -> None:
    save_oauth_store_values(user_id=user_id, values=values, oauth_keys=GOOGLE_OAUTH_KEYS, owner_user_id_key=OAUTH_OWNER_USER_ID_KEY, owner_set_at_key=OAUTH_OWNER_SET_AT_KEY, setup_requests_key=OAUTH_SETUP_REQUESTS_KEY, connector_id=GOOGLE_OAUTH_CONFIG_CONNECTOR_ID, normalize_oauth_setup_requests_fn=_normalize_oauth_setup_requests, tenant_id_for_user_fn=_tenant_id_for_user)
def oauth_configuration_status(user_id: str | None = None) -> dict[str, Any]:
    return oauth_configuration_status_impl(user_id=user_id, oauth_store_values_fn=_oauth_store_values, resolve_google_oauth_config_fn=resolve_google_oauth_config, normalize_oauth_setup_requests_fn=_normalize_oauth_setup_requests, owner_user_id_key=OAUTH_OWNER_USER_ID_KEY, setup_requests_key=OAUTH_SETUP_REQUESTS_KEY, default_redirect_uri=DEFAULT_REDIRECT_URI, default_scopes=list(DEFAULT_SCOPES))
def save_google_oauth_configuration(
    *,
    user_id: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    return save_google_oauth_configuration_impl(user_id=user_id, client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri, oauth_configuration_status_fn=oauth_configuration_status, oauth_store_values_fn=_oauth_store_values, save_oauth_store_values_fn=_save_oauth_store_values, resolve_google_redirect_uri_fn=resolve_google_redirect_uri, iso_now_fn=_iso_now, owner_user_id_key=OAUTH_OWNER_USER_ID_KEY, owner_set_at_key=OAUTH_OWNER_SET_AT_KEY, setup_requests_key=OAUTH_SETUP_REQUESTS_KEY)
def queue_google_oauth_setup_request(
    *,
    user_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    return queue_google_oauth_setup_request_impl(user_id=user_id, note=note, oauth_configuration_status_fn=oauth_configuration_status, oauth_store_values_fn=_oauth_store_values, save_oauth_store_values_fn=_save_oauth_store_values, normalize_oauth_setup_requests_fn=_normalize_oauth_setup_requests, setup_requests_key=OAUTH_SETUP_REQUESTS_KEY, iso_now_fn=_iso_now)
def _parse_token_scopes(payload: dict[str, Any], fallback_scopes: list[str] | None = None) -> list[str]: return parse_token_scopes(payload, fallback_scopes)
def _safe_http_error_message(exc: HTTPError) -> str: return safe_http_error_message(exc)
class GoogleOAuthManager:
    def __init__(self) -> None:
        self.tokens = get_google_token_store()
        self.states = get_oauth_state_store()

    def start_authorization(
        self,
        *,
        user_id: str,
        redirect_uri: str | None = None,
        scopes: list[str] | None = None,
        state: str | None = None,
    ) -> OAuthStartResult:
        config = resolve_google_oauth_config(user_id=user_id)
        client_id = str(config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
        if not client_id:
            raise GoogleOAuthError(
                code="oauth_client_id_missing",
                message="Google OAuth client ID is missing. Save OAuth app credentials in Settings.",
                status_code=400,
            )
        resolved_redirect_uri = resolve_google_redirect_uri(redirect_uri, user_id=user_id)
        resolved_scopes = scopes or _load_default_scopes()
        resolved_state = (state or secrets.token_urlsafe(24)).strip()
        if not resolved_state:
            raise GoogleOAuthError(
                code="oauth_state_missing",
                message="Unable to generate OAuth state.",
                status_code=500,
            )

        self.states.purge_expired()
        self.states.create_state(
            state=resolved_state,
            user_id=user_id,
            redirect_uri=resolved_redirect_uri,
            scopes=resolved_scopes,
        )

        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": resolved_redirect_uri,
                "response_type": "code",
                "scope": " ".join(resolved_scopes),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": resolved_state,
            }
        )
        return OAuthStartResult(
            authorize_url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}",
            state=resolved_state,
            redirect_uri=resolved_redirect_uri,
            scopes=resolved_scopes,
        )

    def consume_state(self, *, state: str) -> OAuthStateRecord:
        record = self.states.consume_state(state=state)
        if record is None:
            raise GoogleOAuthError(
                code="oauth_state_invalid",
                message="OAuth state is invalid, missing, or expired.",
                status_code=401,
            )
        return record

    def exchange_code(
        self,
        *,
        code: str,
        user_id: str,
        redirect_uri: str,
        scopes_hint: list[str] | None = None,
    ) -> GoogleTokenRecord:
        config = resolve_google_oauth_config(user_id=user_id)
        client_id = str(config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
        client_secret = str(config.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
        if not client_id or not client_secret:
            raise GoogleOAuthError(
                code="oauth_client_secret_missing",
                message="Google OAuth client credentials are required. Save OAuth app credentials in Settings.",
                status_code=400,
            )
        body = urlencode(
            {
                "code": code.strip(),
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        request = Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GoogleOAuthError(
                code="oauth_exchange_failed",
                message=f"Google OAuth code exchange failed: {_safe_http_error_message(exc)}",
                status_code=400,
            ) from exc
        except Exception as exc:
            raise GoogleOAuthError(
                code="oauth_exchange_failed",
                message=f"Google OAuth code exchange failed: {exc}",
                status_code=400,
            ) from exc

        if not isinstance(payload, dict):
            raise GoogleOAuthError(
                code="oauth_exchange_invalid_payload",
                message="Google OAuth token endpoint returned invalid payload.",
                status_code=400,
            )

        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise GoogleOAuthError(
                code="oauth_exchange_no_access_token",
                message="Google OAuth exchange did not return access_token.",
                status_code=400,
            )
        scopes = _parse_token_scopes(payload, scopes_hint)
        saved = self.tokens.save_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=str(payload.get("refresh_token") or "").strip(),
            token_type=str(payload.get("token_type") or "Bearer"),
            scopes=scopes,
            expires_in=int(payload.get("expires_in")) if payload.get("expires_in") is not None else None,
            id_token=str(payload.get("id_token")) if payload.get("id_token") else None,
        )
        return saved

    def refresh_tokens(self, *, user_id: str) -> GoogleTokenRecord:
        config = resolve_google_oauth_config(user_id=user_id)
        client_id = str(config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
        client_secret = str(config.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
        if not client_id or not client_secret:
            raise GoogleTokenError(
                code="oauth_client_secret_missing",
                message="Google OAuth client credentials are required. Save OAuth app credentials in Settings.",
                status_code=400,
            )

        record = self.tokens.get_tokens(user_id=user_id)
        if record is None:
            raise GoogleTokenError(
                code="google_tokens_missing",
                message="No Google token record found for this user.",
                status_code=401,
            )
        if not record.refresh_token:
            raise GoogleTokenError(
                code="google_refresh_token_missing",
                message="No refresh_token available. Reconnect Google OAuth.",
                status_code=401,
            )

        body = urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": record.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GoogleTokenError(
                code="google_refresh_failed",
                message=f"Google token refresh failed: {_safe_http_error_message(exc)}",
                status_code=401,
            ) from exc
        except Exception as exc:
            raise GoogleTokenError(
                code="google_refresh_failed",
                message=f"Google token refresh failed: {exc}",
                status_code=401,
            ) from exc
        if not isinstance(payload, dict):
            raise GoogleTokenError(
                code="google_refresh_invalid_payload",
                message="Google refresh endpoint returned invalid payload.",
                status_code=401,
            )
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise GoogleTokenError(
                code="google_refresh_no_access_token",
                message="Google refresh did not return access_token.",
                status_code=401,
            )
        scopes = _parse_token_scopes(payload, record.scopes)
        return self.tokens.save_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=str(payload.get("refresh_token") or "").strip(),
            token_type=str(payload.get("token_type") or record.token_type),
            scopes=scopes,
            expires_in=int(payload.get("expires_in")) if payload.get("expires_in") is not None else None,
            id_token=str(payload.get("id_token")) if payload.get("id_token") else record.id_token,
            email=record.email,
        )

    def ensure_valid_tokens(self, *, user_id: str) -> GoogleTokenRecord:
        record = self.tokens.get_tokens(user_id=user_id)
        if record is None:
            raise GoogleTokenError(
                code="google_tokens_missing",
                message="No Google token record found for this user.",
                status_code=401,
            )
        if record.is_expired():
            return self.refresh_tokens(user_id=user_id)
        return record

    def fetch_user_profile(self, *, user_id: str) -> dict[str, Any]:
        record = self.ensure_valid_tokens(user_id=user_id)
        request = Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            method="GET",
            headers={"Authorization": f"Bearer {record.access_token}"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        email = str(payload.get("email") or "").strip()
        if email and email != (record.email or ""):
            self.tokens.save_tokens(
                user_id=user_id,
                access_token=record.access_token,
                refresh_token=record.refresh_token,
                token_type=record.token_type,
                scopes=record.scopes,
                expires_at=record.expires_at,
                id_token=record.id_token,
                email=email,
            )
        return payload

    def connection_status(self, *, user_id: str) -> dict[str, Any]:
        config = oauth_configuration_status(user_id=user_id)
        selected_services = _saved_oauth_services_for_user(user_id)
        record = self.tokens.get_tokens(user_id=user_id)
        if record is None:
            return {
                "connected": False,
                "scopes": [],
                "email": None,
                "enabled_tools": [],
                "enabled_services": [],
                "oauth_selected_services": selected_services,
                **config,
            }
        try:
            valid = self.ensure_valid_tokens(user_id=user_id)
        except GoogleServiceError:
            return {
                "connected": False,
                "scopes": record.scopes,
                "email": record.email,
                "enabled_tools": enabled_tool_ids_from_scopes(record.scopes),
                "enabled_services": enabled_service_ids_from_scopes(record.scopes),
                "oauth_selected_services": selected_services,
                **config,
            }
        profile = self.fetch_user_profile(user_id=user_id)
        email = str(profile.get("email") or valid.email or "") or None
        return {
            "connected": True,
            "scopes": valid.scopes,
            "email": email,
            "expires_at": valid.expires_at,
            "token_type": valid.token_type,
            "enabled_tools": enabled_tool_ids_from_scopes(valid.scopes),
            "enabled_services": enabled_service_ids_from_scopes(valid.scopes),
            "oauth_selected_services": selected_services,
            **config,
        }

    def disconnect(self, *, user_id: str) -> dict[str, Any]:
        record = self.tokens.get_tokens(user_id=user_id)
        if record is None:
            return {"status": "disconnected", "revoked": False}

        revoked = False
        for token in [record.access_token, record.refresh_token]:
            token = str(token or "").strip()
            if not token:
                continue
            body = urlencode({"token": token}).encode("utf-8")
            request = Request(
                "https://oauth2.googleapis.com/revoke",
                data=body,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                with urlopen(request, timeout=20):
                    revoked = True
            except Exception:
                # Best effort revoke; token file is still cleared below.
                continue
        self.tokens.clear_tokens(user_id=user_id)
        return {"status": "disconnected", "revoked": revoked}


_oauth_manager: GoogleOAuthManager | None = None


def get_google_oauth_manager() -> GoogleOAuthManager:
    global _oauth_manager
    if _oauth_manager is None:
        _oauth_manager = GoogleOAuthManager()
    return _oauth_manager


def build_google_authorize_url(
    *,
    user_id: str,
    redirect_uri: str | None = None,
    scopes: list[str] | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    return get_google_oauth_manager().start_authorization(
        user_id=user_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state=state,
    ).to_dict()


def exchange_google_oauth_code(
    *,
    user_id: str,
    code: str,
    redirect_uri: str,
    scopes_hint: list[str] | None = None,
) -> GoogleTokenRecord:
    return get_google_oauth_manager().exchange_code(
        code=code,
        user_id=user_id,
        redirect_uri=redirect_uri,
        scopes_hint=scopes_hint,
    )
