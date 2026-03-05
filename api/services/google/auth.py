from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
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
    default_oauth_scopes,
    enabled_service_ids_from_scopes,
    enabled_tool_ids_from_scopes,
    normalize_google_oauth_service_ids,
)
from api.services.google.session import GoogleAuthSession  # noqa: F401
from api.services.google.store import GoogleTokenRecord, OAuthStateRecord, get_google_token_store, get_oauth_state_store

DEFAULT_REDIRECT_URI = "http://localhost:8000/api/agent/oauth/google/callback"
DEFAULT_FRONTEND_SUCCESS_URL = "http://localhost:5173/settings?oauth=success"
DEFAULT_FRONTEND_ERROR_URL = "http://localhost:5173/settings?oauth=error"
DEFAULT_SCOPES = default_oauth_scopes()
GOOGLE_OAUTH_CONFIG_CONNECTOR_ID = "google_oauth"
GOOGLE_OAUTH_KEYS = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
)
OAUTH_OWNER_USER_ID_KEY = "MAIA_OAUTH_OWNER_USER_ID"
OAUTH_OWNER_SET_AT_KEY = "MAIA_OAUTH_OWNER_SET_AT"
OAUTH_SETUP_REQUESTS_KEY = "MAIA_OAUTH_SETUP_REQUESTS"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _oauth_env(name: str) -> str:
    return str(os.getenv(name, "")).strip()


def _load_default_scopes() -> list[str]:
    raw = _oauth_env("GOOGLE_OAUTH_SCOPES")
    if not raw:
        return list(DEFAULT_SCOPES)
    parts = [item.strip() for item in raw.replace(";", ",").split(",")]
    return [item for item in parts if item]


def _tenant_id_for_user(user_id: str) -> str:
    try:
        from api.context import get_context
        from api.services.settings_service import load_user_settings

        settings = load_user_settings(get_context(), user_id)
        tenant_id = str(settings.get("agent.tenant_id") or "").strip()
        return tenant_id or user_id
    except Exception:
        return user_id


def _saved_oauth_services_for_user(user_id: str | None) -> list[str]:
    if not user_id:
        return []
    try:
        from api.context import get_context
        from api.services.settings_service import load_user_settings

        settings = load_user_settings(get_context(), user_id)
    except Exception:
        return []
    return normalize_google_oauth_service_ids(settings.get("agent.google_oauth_services"))


def _oauth_store_values(
    user_id: str | None = None,
    *,
    include_metadata: bool = False,
) -> dict[str, Any]:
    if not user_id:
        return {}
    try:
        from api.services.agent.auth.credentials import get_credential_store

        record = get_credential_store().get(
            tenant_id=_tenant_id_for_user(user_id),
            connector_id=GOOGLE_OAUTH_CONFIG_CONNECTOR_ID,
        )
    except Exception:
        return {}
    if record is None:
        return {}
    values: dict[str, Any] = {}
    for key in GOOGLE_OAUTH_KEYS:
        values[key] = str(record.values.get(key) or "").strip()
    if include_metadata:
        values[OAUTH_OWNER_USER_ID_KEY] = str(record.values.get(OAUTH_OWNER_USER_ID_KEY) or "").strip()
        values[OAUTH_OWNER_SET_AT_KEY] = str(record.values.get(OAUTH_OWNER_SET_AT_KEY) or "").strip()
        values[OAUTH_SETUP_REQUESTS_KEY] = record.values.get(OAUTH_SETUP_REQUESTS_KEY)
    return values


def resolve_google_oauth_config(user_id: str | None = None) -> dict[str, str]:
    merged = {key: _oauth_env(key) for key in GOOGLE_OAUTH_KEYS}
    stored = _oauth_store_values(user_id=user_id)
    for key, value in stored.items():
        if value:
            merged[key] = value
    merged["GOOGLE_OAUTH_REDIRECT_URI"] = merged.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip() or DEFAULT_REDIRECT_URI
    return merged


def resolve_google_redirect_uri(override: str | None = None, *, user_id: str | None = None) -> str:
    explicit = str(override or "").strip()
    if explicit:
        return explicit
    return resolve_google_oauth_config(user_id=user_id)["GOOGLE_OAUTH_REDIRECT_URI"]


def _normalize_oauth_setup_requests(raw: Any) -> list[dict[str, str]]:
    rows = raw
    if isinstance(raw, str):
        try:
            rows = json.loads(raw)
        except Exception:
            rows = []
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        request_id = str(item.get("id") or "").strip()
        requester_user_id = str(item.get("requester_user_id") or "").strip()
        if not request_id or not requester_user_id:
            continue
        status = str(item.get("status") or "pending").strip().lower() or "pending"
        if status not in {"pending", "resolved", "dismissed"}:
            status = "pending"
        normalized.append(
            {
                "id": request_id,
                "requester_user_id": requester_user_id,
                "note": str(item.get("note") or "").strip()[:300],
                "status": status,
                "requested_at": str(item.get("requested_at") or "").strip() or _iso_now(),
                "resolved_at": str(item.get("resolved_at") or "").strip(),
                "resolved_by": str(item.get("resolved_by") or "").strip(),
            }
        )
    normalized.sort(key=lambda row: row.get("requested_at") or "", reverse=True)
    return normalized[:60]


def _save_oauth_store_values(user_id: str, values: dict[str, Any]) -> None:
    from api.services.agent.auth.credentials import get_credential_store

    cleaned: dict[str, Any] = {}
    for key in GOOGLE_OAUTH_KEYS:
        cleaned[key] = str(values.get(key) or "").strip()
    cleaned[OAUTH_OWNER_USER_ID_KEY] = str(values.get(OAUTH_OWNER_USER_ID_KEY) or "").strip()
    cleaned[OAUTH_OWNER_SET_AT_KEY] = str(values.get(OAUTH_OWNER_SET_AT_KEY) or "").strip()
    cleaned[OAUTH_SETUP_REQUESTS_KEY] = _normalize_oauth_setup_requests(values.get(OAUTH_SETUP_REQUESTS_KEY))
    get_credential_store().set(
        tenant_id=_tenant_id_for_user(user_id),
        connector_id=GOOGLE_OAUTH_CONFIG_CONNECTOR_ID,
        values=cleaned,
    )


def oauth_configuration_status(user_id: str | None = None) -> dict[str, Any]:
    config = resolve_google_oauth_config(user_id=user_id)
    missing_env = [
        name
        for name in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")
        if not str(config.get(name) or "").strip()
    ]
    stored = _oauth_store_values(user_id=user_id, include_metadata=True)
    stored_client_id = str(stored.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    stored_client_secret = str(stored.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    uses_stored_credentials = bool(stored_client_id or stored_client_secret)
    owner_user_id = str(stored.get(OAUTH_OWNER_USER_ID_KEY) or "").strip()
    normalized_owner_user_id = owner_user_id or None
    setup_requests = _normalize_oauth_setup_requests(stored.get(OAUTH_SETUP_REQUESTS_KEY))
    pending_requests = [row for row in setup_requests if row.get("status") == "pending"]
    pending_for_current_user = bool(
        user_id and any(str(row.get("requester_user_id") or "").strip() == str(user_id).strip() for row in pending_requests)
    )
    oauth_ready = len(missing_env) == 0
    managed_by_env = oauth_ready and not uses_stored_credentials
    oauth_can_manage_config = bool(user_id)
    if normalized_owner_user_id:
        oauth_can_manage_config = str(normalized_owner_user_id) == str(user_id or "")
    elif managed_by_env:
        oauth_can_manage_config = False
    return {
        "oauth_ready": oauth_ready,
        "oauth_missing_env": missing_env,
        "oauth_redirect_uri": str(config.get("GOOGLE_OAUTH_REDIRECT_URI") or DEFAULT_REDIRECT_URI),
        "oauth_client_id_configured": bool(str(config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()),
        "oauth_client_secret_configured": bool(str(config.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()),
        "oauth_uses_stored_credentials": uses_stored_credentials,
        "oauth_workspace_owner_user_id": normalized_owner_user_id,
        "oauth_current_user_is_owner": bool(
            normalized_owner_user_id and str(normalized_owner_user_id) == str(user_id or "")
        ),
        "oauth_can_manage_config": oauth_can_manage_config,
        "oauth_setup_request_pending": pending_for_current_user,
        "oauth_setup_request_count": len(pending_requests),
        "oauth_managed_by_env": managed_by_env,
        "oauth_default_scopes": list(DEFAULT_SCOPES),
    }


def save_google_oauth_configuration(
    *,
    user_id: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    if not str(client_id or "").strip() or not str(client_secret or "").strip():
        raise GoogleOAuthError(
            code="oauth_config_incomplete",
            message="Google OAuth client ID and client secret are required.",
            status_code=400,
        )

    status = oauth_configuration_status(user_id=user_id)
    if not bool(status.get("oauth_can_manage_config")):
        owner_user_id = str(status.get("oauth_workspace_owner_user_id") or "").strip()
        raise GoogleOAuthError(
            code="oauth_config_workspace_owner_required",
            message="Only the workspace OAuth owner can update Google OAuth app credentials.",
            status_code=403,
            details={"workspace_owner_user_id": owner_user_id} if owner_user_id else {},
        )

    values = _oauth_store_values(user_id=user_id, include_metadata=True)
    values["GOOGLE_OAUTH_CLIENT_ID"] = str(client_id or "").strip()
    values["GOOGLE_OAUTH_CLIENT_SECRET"] = str(client_secret or "").strip()
    values["GOOGLE_OAUTH_REDIRECT_URI"] = (
        str(redirect_uri or "").strip() or resolve_google_redirect_uri(user_id=user_id)
    )
    if not str(values.get(OAUTH_OWNER_USER_ID_KEY) or "").strip():
        values[OAUTH_OWNER_USER_ID_KEY] = user_id
        values[OAUTH_OWNER_SET_AT_KEY] = _iso_now()
    values[OAUTH_SETUP_REQUESTS_KEY] = []
    _save_oauth_store_values(user_id, values)
    return oauth_configuration_status(user_id=user_id)


def queue_google_oauth_setup_request(
    *,
    user_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    status = oauth_configuration_status(user_id=user_id)
    if bool(status.get("oauth_can_manage_config")):
        raise GoogleOAuthError(
            code="oauth_setup_request_not_needed",
            message="This user can configure Google OAuth app credentials directly.",
            status_code=400,
        )

    values = _oauth_store_values(user_id=user_id, include_metadata=True)
    requests = _normalize_oauth_setup_requests(values.get(OAUTH_SETUP_REQUESTS_KEY))
    existing = next(
        (
            row
            for row in requests
            if row.get("status") == "pending"
            and str(row.get("requester_user_id") or "").strip() == str(user_id).strip()
        ),
        None,
    )
    if existing is None:
        existing = {
            "id": secrets.token_urlsafe(10),
            "requester_user_id": user_id,
            "note": str(note or "").strip()[:300],
            "status": "pending",
            "requested_at": _iso_now(),
            "resolved_at": "",
            "resolved_by": "",
        }
        requests.insert(0, existing)
        values[OAUTH_SETUP_REQUESTS_KEY] = requests
        _save_oauth_store_values(user_id, values)

    pending_count = len([row for row in requests if row.get("status") == "pending"])
    return {
        "status": "queued",
        "request": existing,
        "pending_count": pending_count,
        "workspace_owner_user_id": status.get("oauth_workspace_owner_user_id"),
    }


def _parse_token_scopes(payload: dict[str, Any], fallback_scopes: list[str] | None = None) -> list[str]:
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        return [item for item in raw_scope.split(" ") if item]
    return list(fallback_scopes or [])


def _safe_http_error_message(exc: HTTPError) -> str:
    try:
        detail = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        detail = ""
    return detail[:300] if detail else f"HTTP {exc.code}"


@dataclass
class OAuthStartResult:
    authorize_url: str
    state: str
    redirect_uri: str
    scopes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorize_url": self.authorize_url,
            "state": self.state,
            "redirect_uri": self.redirect_uri,
            "scopes": self.scopes,
        }


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
