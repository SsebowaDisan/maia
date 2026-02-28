from __future__ import annotations

from dataclasses import dataclass
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
from api.services.google.session import GoogleAuthSession  # noqa: F401
from api.services.google.store import GoogleTokenRecord, OAuthStateRecord, get_google_token_store, get_oauth_state_store

DEFAULT_REDIRECT_URI = "http://localhost:8000/api/agent/oauth/google/callback"
DEFAULT_FRONTEND_SUCCESS_URL = "http://localhost:5173/settings?oauth=success"
DEFAULT_FRONTEND_ERROR_URL = "http://localhost:5173/settings?oauth=error"
DEFAULT_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/analytics.readonly",
]
def _oauth_env(name: str) -> str:
    return str(os.getenv(name, "")).strip()


def _load_default_scopes() -> list[str]:
    raw = _oauth_env("GOOGLE_OAUTH_SCOPES")
    if not raw:
        return list(DEFAULT_SCOPES)
    parts = [item.strip() for item in raw.replace(";", ",").split(",")]
    return [item for item in parts if item]


def resolve_google_redirect_uri(override: str | None = None) -> str:
    return (override or _oauth_env("GOOGLE_OAUTH_REDIRECT_URI") or DEFAULT_REDIRECT_URI).strip()


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
        client_id = _oauth_env("GOOGLE_OAUTH_CLIENT_ID")
        if not client_id:
            raise GoogleOAuthError(
                code="oauth_client_id_missing",
                message="GOOGLE_OAUTH_CLIENT_ID is not configured.",
                status_code=400,
            )
        resolved_redirect_uri = resolve_google_redirect_uri(redirect_uri)
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
        client_id = _oauth_env("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = _oauth_env("GOOGLE_OAUTH_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise GoogleOAuthError(
                code="oauth_client_secret_missing",
                message="GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are required.",
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
        client_id = _oauth_env("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = _oauth_env("GOOGLE_OAUTH_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise GoogleTokenError(
                code="oauth_client_secret_missing",
                message="GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are required.",
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
        record = self.tokens.get_tokens(user_id=user_id)
        if record is None:
            return {"connected": False, "scopes": [], "email": None}
        try:
            valid = self.ensure_valid_tokens(user_id=user_id)
        except GoogleServiceError:
            return {"connected": False, "scopes": record.scopes, "email": record.email}
        profile = self.fetch_user_profile(user_id=user_id)
        email = str(profile.get("email") or valid.email or "") or None
        return {
            "connected": True,
            "scopes": valid.scopes,
            "email": email,
            "expires_at": valid.expires_at,
            "token_type": valid.token_type,
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
