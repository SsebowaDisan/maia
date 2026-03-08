from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import secrets
from typing import Any
from urllib.error import HTTPError

from api.services.google.errors import GoogleOAuthError
from api.services.google.oauth_scopes import default_oauth_scopes, normalize_google_oauth_service_ids


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def oauth_env(name: str) -> str:
    return str(os.getenv(name, "")).strip()


def load_default_scopes() -> list[str]:
    raw = oauth_env("GOOGLE_OAUTH_SCOPES")
    if not raw:
        return list(default_oauth_scopes())
    parts = [item.strip() for item in raw.replace(";", ",").split(",")]
    return [item for item in parts if item]


def tenant_id_for_user(user_id: str) -> str:
    try:
        from api.context import get_context
        from api.services.settings_service import load_user_settings

        settings = load_user_settings(get_context(), user_id)
        tenant_id = str(settings.get("agent.tenant_id") or "").strip()
        return tenant_id or user_id
    except Exception:
        return user_id


def saved_oauth_services_for_user(user_id: str | None) -> list[str]:
    if not user_id:
        return []
    try:
        from api.context import get_context
        from api.services.settings_service import load_user_settings

        settings = load_user_settings(get_context(), user_id)
    except Exception:
        return []
    return normalize_google_oauth_service_ids(settings.get("agent.google_oauth_services"))


def oauth_store_values(
    user_id: str | None,
    *,
    include_metadata: bool,
    tenant_id_for_user_fn,
    oauth_keys: tuple[str, ...],
    owner_user_id_key: str,
    owner_set_at_key: str,
    setup_requests_key: str,
    connector_id: str,
) -> dict[str, Any]:
    if not user_id:
        return {}
    try:
        from api.services.agent.auth.credentials import get_credential_store

        record = get_credential_store().get(
            tenant_id=tenant_id_for_user_fn(user_id),
            connector_id=connector_id,
        )
    except Exception:
        return {}
    if record is None:
        return {}
    values: dict[str, Any] = {}
    for key in oauth_keys:
        values[key] = str(record.values.get(key) or "").strip()
    if include_metadata:
        values[owner_user_id_key] = str(record.values.get(owner_user_id_key) or "").strip()
        values[owner_set_at_key] = str(record.values.get(owner_set_at_key) or "").strip()
        values[setup_requests_key] = record.values.get(setup_requests_key)
    return values


def resolve_google_oauth_config_impl(
    *,
    user_id: str | None,
    oauth_keys: tuple[str, ...],
    oauth_env_fn,
    oauth_store_values_fn,
    default_redirect_uri: str,
) -> dict[str, str]:
    merged = {key: oauth_env_fn(key) for key in oauth_keys}
    stored = oauth_store_values_fn(user_id=user_id)
    for key, value in stored.items():
        if value:
            merged[key] = value
    merged["GOOGLE_OAUTH_REDIRECT_URI"] = merged.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip() or default_redirect_uri
    return merged


def resolve_google_redirect_uri_impl(
    *,
    override: str | None,
    user_id: str | None,
    resolve_google_oauth_config_fn,
) -> str:
    explicit = str(override or "").strip()
    if explicit:
        return explicit
    return resolve_google_oauth_config_fn(user_id=user_id)["GOOGLE_OAUTH_REDIRECT_URI"]


def normalize_oauth_setup_requests(raw: Any, *, iso_now_fn) -> list[dict[str, str]]:
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
                "requested_at": str(item.get("requested_at") or "").strip() or iso_now_fn(),
                "resolved_at": str(item.get("resolved_at") or "").strip(),
                "resolved_by": str(item.get("resolved_by") or "").strip(),
            }
        )
    normalized.sort(key=lambda row: row.get("requested_at") or "", reverse=True)
    return normalized[:60]


def save_oauth_store_values(
    *,
    user_id: str,
    values: dict[str, Any],
    oauth_keys: tuple[str, ...],
    owner_user_id_key: str,
    owner_set_at_key: str,
    setup_requests_key: str,
    connector_id: str,
    normalize_oauth_setup_requests_fn,
    tenant_id_for_user_fn,
) -> None:
    from api.services.agent.auth.credentials import get_credential_store

    cleaned: dict[str, Any] = {}
    for key in oauth_keys:
        cleaned[key] = str(values.get(key) or "").strip()
    cleaned[owner_user_id_key] = str(values.get(owner_user_id_key) or "").strip()
    cleaned[owner_set_at_key] = str(values.get(owner_set_at_key) or "").strip()
    cleaned[setup_requests_key] = normalize_oauth_setup_requests_fn(values.get(setup_requests_key))
    get_credential_store().set(
        tenant_id=tenant_id_for_user_fn(user_id),
        connector_id=connector_id,
        values=cleaned,
    )


def oauth_configuration_status_impl(
    *,
    user_id: str | None,
    oauth_store_values_fn,
    resolve_google_oauth_config_fn,
    normalize_oauth_setup_requests_fn,
    owner_user_id_key: str,
    setup_requests_key: str,
    default_redirect_uri: str,
    default_scopes: list[str],
) -> dict[str, Any]:
    config = resolve_google_oauth_config_fn(user_id=user_id)
    missing_env = [
        name
        for name in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")
        if not str(config.get(name) or "").strip()
    ]
    stored = oauth_store_values_fn(user_id=user_id, include_metadata=True)
    stored_client_id = str(stored.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    stored_client_secret = str(stored.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    uses_stored_credentials = bool(stored_client_id or stored_client_secret)
    owner_user_id = str(stored.get(owner_user_id_key) or "").strip()
    normalized_owner_user_id = owner_user_id or None
    setup_requests = normalize_oauth_setup_requests_fn(stored.get(setup_requests_key))
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
        "oauth_redirect_uri": str(config.get("GOOGLE_OAUTH_REDIRECT_URI") or default_redirect_uri),
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
        "oauth_default_scopes": list(default_scopes),
    }


def save_google_oauth_configuration_impl(
    *,
    user_id: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str | None,
    oauth_configuration_status_fn,
    oauth_store_values_fn,
    save_oauth_store_values_fn,
    resolve_google_redirect_uri_fn,
    iso_now_fn,
    owner_user_id_key: str,
    owner_set_at_key: str,
    setup_requests_key: str,
) -> dict[str, Any]:
    if not str(client_id or "").strip() or not str(client_secret or "").strip():
        raise GoogleOAuthError(
            code="oauth_config_incomplete",
            message="Google OAuth client ID and client secret are required.",
            status_code=400,
        )

    status = oauth_configuration_status_fn(user_id=user_id)
    if not bool(status.get("oauth_can_manage_config")):
        owner_user_id = str(status.get("oauth_workspace_owner_user_id") or "").strip()
        raise GoogleOAuthError(
            code="oauth_config_workspace_owner_required",
            message="Only the workspace OAuth owner can update Google OAuth app credentials.",
            status_code=403,
            details={"workspace_owner_user_id": owner_user_id} if owner_user_id else {},
        )

    values = oauth_store_values_fn(user_id=user_id, include_metadata=True)
    values["GOOGLE_OAUTH_CLIENT_ID"] = str(client_id or "").strip()
    values["GOOGLE_OAUTH_CLIENT_SECRET"] = str(client_secret or "").strip()
    values["GOOGLE_OAUTH_REDIRECT_URI"] = str(redirect_uri or "").strip() or resolve_google_redirect_uri_fn(user_id=user_id)
    if not str(values.get(owner_user_id_key) or "").strip():
        values[owner_user_id_key] = user_id
        values[owner_set_at_key] = iso_now_fn()
    values[setup_requests_key] = []
    save_oauth_store_values_fn(user_id, values)
    return oauth_configuration_status_fn(user_id=user_id)


def queue_google_oauth_setup_request_impl(
    *,
    user_id: str,
    note: str | None,
    oauth_configuration_status_fn,
    oauth_store_values_fn,
    save_oauth_store_values_fn,
    normalize_oauth_setup_requests_fn,
    setup_requests_key: str,
    iso_now_fn,
) -> dict[str, Any]:
    status = oauth_configuration_status_fn(user_id=user_id)
    if bool(status.get("oauth_can_manage_config")):
        raise GoogleOAuthError(
            code="oauth_setup_request_not_needed",
            message="This user can configure Google OAuth app credentials directly.",
            status_code=400,
        )

    values = oauth_store_values_fn(user_id=user_id, include_metadata=True)
    requests = normalize_oauth_setup_requests_fn(values.get(setup_requests_key))
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
            "requested_at": iso_now_fn(),
            "resolved_at": "",
            "resolved_by": "",
        }
        requests.insert(0, existing)
        values[setup_requests_key] = requests
        save_oauth_store_values_fn(user_id, values)

    pending_count = len([row for row in requests if row.get("status") == "pending"])
    return {
        "status": "queued",
        "request": existing,
        "pending_count": pending_count,
        "workspace_owner_user_id": status.get("oauth_workspace_owner_user_id"),
    }


def parse_token_scopes(payload: dict[str, Any], fallback_scopes: list[str] | None = None) -> list[str]:
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, str) and raw_scope.strip():
        return [item for item in raw_scope.split(" ") if item]
    return list(fallback_scopes or [])


def safe_http_error_message(exc: HTTPError) -> str:
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
