from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from api.services.google.errors import GoogleTokenError

DEFAULT_SERVICE_ACCOUNT_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
)
VALID_AUTH_MODES = {"oauth", "service_account"}

_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}
_TOKEN_CACHE_LOCK = Lock()


@dataclass
class ServiceAccountProfile:
    configured: bool
    usable: bool
    email: str
    client_id: str
    project_id: str
    source: str
    auth_mode: str
    message: str
    instructions: list[str]


def resolve_google_auth_mode(*, settings: dict[str, Any] | None = None) -> str:
    configured = (
        str((settings or {}).get("agent.google_auth_mode") or "").strip().lower()
        or str(os.getenv("GOOGLE_AUTH_MODE", "")).strip().lower()
    )
    if configured in VALID_AUTH_MODES:
        return configured
    return "oauth"


def _read_file(path_text: str) -> str:
    path = Path(path_text).expanduser()
    if not path.exists() or not path.is_file():
        raise GoogleTokenError(
            code="google_service_account_file_missing",
            message=f"Service-account key file not found: {path}",
            status_code=400,
        )
    return path.read_text(encoding="utf-8")


def _normalize_json_payload(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        payload = raw_value
    else:
        try:
            payload = json.loads(str(raw_value or ""))
        except Exception as exc:
            raise GoogleTokenError(
                code="google_service_account_invalid_json",
                message=f"Invalid service-account JSON: {exc}",
                status_code=400,
            ) from exc
    if not isinstance(payload, dict):
        raise GoogleTokenError(
            code="google_service_account_invalid_json",
            message="Service-account key must be a JSON object.",
            status_code=400,
        )
    if str(payload.get("type") or "").strip() != "service_account":
        raise GoogleTokenError(
            code="google_service_account_invalid_type",
            message="Provided JSON is not a Google service-account key.",
            status_code=400,
        )
    if not str(payload.get("client_email") or "").strip():
        raise GoogleTokenError(
            code="google_service_account_email_missing",
            message="Service-account JSON does not include client_email.",
            status_code=400,
        )
    if not str(payload.get("private_key") or "").strip():
        raise GoogleTokenError(
            code="google_service_account_key_missing",
            message="Service-account JSON does not include private_key.",
            status_code=400,
        )
    return payload


def _load_service_account_info(
    *,
    settings: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    source_candidates: list[tuple[str, str]] = [
        (
            "settings.agent.google_service_account_json",
            str((settings or {}).get("agent.google_service_account_json") or "").strip(),
        ),
        (
            "env.GOOGLE_SERVICE_ACCOUNT_JSON",
            str(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")).strip(),
        ),
    ]
    for source, value in source_candidates:
        if not value:
            continue
        return _normalize_json_payload(value), source

    path_candidates: list[tuple[str, str]] = [
        (
            "settings.agent.google_service_account_json_path",
            str((settings or {}).get("agent.google_service_account_json_path") or "").strip(),
        ),
        (
            "env.GOOGLE_SERVICE_ACCOUNT_JSON_PATH",
            str(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")).strip(),
        ),
        (
            "env.MAIA_GMAIL_SA_JSON_PATH",
            str(os.getenv("MAIA_GMAIL_SA_JSON_PATH", "")).strip(),
        ),
    ]
    for source, value in path_candidates:
        if not value:
            continue
        return _normalize_json_payload(_read_file(value)), source
    return None, ""


def _resolve_service_account_subject(*, settings: dict[str, Any] | None) -> str:
    return (
        str((settings or {}).get("agent.google_service_account_impersonate") or "").strip()
        or str(os.getenv("GOOGLE_SERVICE_ACCOUNT_IMPERSONATE", "")).strip()
        or str(os.getenv("MAIA_GMAIL_IMPERSONATE", "")).strip()
    )


def resolve_service_account_profile(
    *,
    settings: dict[str, Any] | None = None,
) -> ServiceAccountProfile:
    auth_mode = resolve_google_auth_mode(settings=settings)
    instructions = [
        "Copy the service-account email and add it to the target Google resource sharing dialog.",
        "Assign Reader/Viewer for read-only access, or Editor for write access.",
        "For GA4, add the service account in Property Access Management with at least Viewer role.",
    ]
    email_override = (
        str((settings or {}).get("agent.google_service_account_email") or "").strip()
        or str(os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")).strip()
    )
    info, source = _load_service_account_info(settings=settings)
    if info is None:
        if email_override:
            return ServiceAccountProfile(
                configured=True,
                usable=False,
                email=email_override,
                client_id="",
                project_id="",
                source="settings/email_only",
                auth_mode=auth_mode,
                message="Email is available for sharing, but key JSON is missing for API access.",
                instructions=instructions,
            )
        return ServiceAccountProfile(
            configured=False,
            usable=False,
            email="",
            client_id="",
            project_id="",
            source="",
            auth_mode=auth_mode,
            message="Service-account credentials are not configured.",
            instructions=instructions,
        )
    email = str(info.get("client_email") or "").strip()
    return ServiceAccountProfile(
        configured=True,
        usable=True,
        email=email,
        client_id=str(info.get("client_id") or "").strip(),
        project_id=str(info.get("project_id") or "").strip(),
        source=source,
        auth_mode=auth_mode,
        message="Service account is configured and ready.",
        instructions=instructions,
    )


def _scope_key(scopes: list[str]) -> str:
    return " ".join(sorted({item for item in scopes if item}))


def issue_service_account_access_token(
    *,
    settings: dict[str, Any] | None = None,
    scopes: list[str] | None = None,
) -> str:
    info, source = _load_service_account_info(settings=settings)
    if info is None:
        raise GoogleTokenError(
            code="google_service_account_missing",
            message=(
                "Service-account mode is enabled but no key JSON is configured. "
                "Set GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_SERVICE_ACCOUNT_JSON_PATH."
            ),
            status_code=401,
        )
    effective_scopes = [str(item).strip() for item in (scopes or DEFAULT_SERVICE_ACCOUNT_SCOPES) if str(item).strip()]
    if not effective_scopes:
        raise GoogleTokenError(
            code="google_service_account_scopes_missing",
            message="No OAuth scopes were provided for the service-account token.",
            status_code=400,
        )
    subject = _resolve_service_account_subject(settings=settings)
    cache_key = (
        f"{str(info.get('client_email') or '').strip()}|"
        f"{str(info.get('private_key_id') or '').strip()}|"
        f"{subject}|{_scope_key(effective_scopes)}"
    )
    now = datetime.now(timezone.utc)
    with _TOKEN_CACHE_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached is not None:
            token, expires_at = cached
            if token and expires_at > now + timedelta(seconds=45):
                return token

    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import service_account
    except Exception as exc:
        raise GoogleTokenError(
            code="google_service_account_dependency_missing",
            message=(
                "google-auth dependency is missing. Install package `google-auth` "
                "to enable service-account mode."
            ),
            status_code=500,
        ) from exc

    try:
        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=effective_scopes,
        )
        if subject:
            credentials = credentials.with_subject(subject)
        credentials.refresh(GoogleRequest())
    except GoogleTokenError:
        raise
    except Exception as exc:
        raise GoogleTokenError(
            code="google_service_account_token_failed",
            message=f"Unable to mint service-account access token from {source}: {exc}",
            status_code=401,
        ) from exc

    token = str(getattr(credentials, "token", "") or "").strip()
    expiry = getattr(credentials, "expiry", None)
    if not token:
        raise GoogleTokenError(
            code="google_service_account_token_missing",
            message="Service-account credential refresh succeeded but no access token was returned.",
            status_code=401,
        )
    if not isinstance(expiry, datetime):
        expiry = now + timedelta(minutes=45)
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE[cache_key] = (token, expiry.astimezone(timezone.utc))
    return token
