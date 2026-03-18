from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import HTTPException

from api.context import get_context
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.connectors.registry import get_connector_registry
from api.services.google.auth import (
    DEFAULT_FRONTEND_ERROR_URL,
    DEFAULT_FRONTEND_SUCCESS_URL,
)
from api.services.google.errors import GoogleServiceError
from api.services.settings_service import load_user_settings


def tenant_id_for_user(user_id: str) -> str:
    settings = load_user_settings(get_context(), user_id)
    return str(settings.get("agent.tenant_id") or user_id)


def mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"


def masked_credential_payload(values: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, raw_value in values.items():
        if raw_value is None:
            masked[key] = ""
            continue
        text = str(raw_value)
        if "token" in key.lower() or "secret" in key.lower() or "password" in key.lower():
            masked[key] = mask_secret(text)
        else:
            masked[key] = text
    return masked


def http_error_from_google(exc: GoogleServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.to_detail())


def oauth_error(status_code: int, code: str, message: str, **details: Any) -> HTTPException:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return HTTPException(status_code=status_code, detail=payload)


def to_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def build_frontend_redirect(
    *,
    oauth_status: str,
    code: str | None = None,
    message: str | None = None,
) -> str:
    if oauth_status == "success":
        base_url = os.getenv("GOOGLE_OAUTH_FRONTEND_SUCCESS_URL", DEFAULT_FRONTEND_SUCCESS_URL)
    else:
        base_url = os.getenv("GOOGLE_OAUTH_FRONTEND_ERROR_URL", DEFAULT_FRONTEND_ERROR_URL)
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["oauth"] = oauth_status
    if code:
        query["code"] = code
    if message:
        query["message"] = message[:220]
    return urlunparse(parsed._replace(query=urlencode(query)))


def store_google_connector_tokens(
    *,
    user_id: str,
    access_token: str,
    refresh_token: str,
    connector_ids: list[str],
) -> list[str]:
    tenant_id = tenant_id_for_user(user_id)
    stored_connectors: list[str] = []
    for connector_id in connector_ids:
        if connector_id not in get_connector_registry().names():
            continue
        # Generic OAuth credential mapping — derive env key prefix from connector_id
        env_prefix = connector_id.upper().replace("-", "_")
        credential_values: dict[str, Any] = {
            f"{env_prefix}_ACCESS_TOKEN": access_token,
        }
        if refresh_token:
            credential_values[f"{env_prefix}_REFRESH_TOKEN"] = refresh_token
        get_credential_store().set(
            tenant_id=tenant_id,
            connector_id=connector_id,
            values=credential_values,
        )
        stored_connectors.append(connector_id)
    return stored_connectors
