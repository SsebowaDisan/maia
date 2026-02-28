from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from fastapi import HTTPException

from api.context import get_context
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.live_events import get_live_event_broker
from api.services.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    OllamaError,
    normalize_ollama_base_url,
)
from api.services.settings_service import load_user_settings, save_user_settings

MAPS_CONNECTOR_ID = "google_maps"
BRAVE_CONNECTOR_ID = "brave_search"


def tenant_settings(user_id: str) -> tuple[str, dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    return tenant_id, settings


def resolve_maps_env_key() -> str:
    return (
        str(os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()
        or str(os.getenv("GOOGLE_PLACES_API_KEY", "")).strip()
        or str(os.getenv("GOOGLE_GEO_API_KEY", "")).strip()
    )


def resolve_brave_env_key() -> str:
    return str(os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()


def resolve_ollama_base_url(
    *,
    settings: dict[str, Any],
    override: str | None = None,
) -> str:
    candidate = (
        str(override or "").strip()
        or str(settings.get("agent.ollama.base_url") or "").strip()
        or str(os.getenv("OLLAMA_BASE_URL", "")).strip()
        or DEFAULT_OLLAMA_BASE_URL
    )
    return normalize_ollama_base_url(candidate)


def stored_secret(tenant_id: str, connector_id: str, key_name: str) -> str:
    record = get_credential_store().get(tenant_id=tenant_id, connector_id=connector_id)
    if record is None:
        return ""
    return str(record.values.get(key_name) or "").strip()


def publish_event(
    *,
    user_id: str,
    run_id: str | None,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    payload = {
        "type": event_type,
        "message": message,
        "data": dict(data or {}),
    }
    get_live_event_broker().publish(user_id=user_id, run_id=run_id, event=payload)


def raise_http_from_ollama(exc: OllamaError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


def save_ollama_settings(
    *,
    user_id: str,
    existing_settings: dict[str, Any],
    base_url: str,
    default_model: str | None = None,
    embedding_model: str | None = None,
) -> None:
    next_settings = deepcopy(existing_settings)
    next_settings["agent.ollama.base_url"] = normalize_ollama_base_url(base_url)
    if default_model is not None:
        next_settings["agent.ollama.default_model"] = str(default_model).strip()
    if embedding_model is not None:
        next_settings["agent.ollama.embedding_model"] = str(embedding_model).strip()
    save_user_settings(
        context=get_context(),
        user_id=user_id,
        values=next_settings,
    )
