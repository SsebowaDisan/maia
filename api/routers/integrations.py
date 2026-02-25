from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_current_user_id
from api.context import get_context
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.live_events import get_live_event_broker
from api.services.settings_service import load_user_settings
from api.services.search.brave_search import BraveSearchService
from api.services.search.errors import BraveSearchError

router = APIRouter(prefix="/api/agent", tags=["agent-integrations"])

MAPS_CONNECTOR_ID = "google_maps"
BRAVE_CONNECTOR_ID = "brave_search"


class MapsSaveRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=512)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    count: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=200)
    country: str = Field(default="BE", min_length=2, max_length=2)
    safesearch: str = Field(default="moderate", min_length=2, max_length=20)
    domain: str | None = Field(default=None, max_length=255)
    run_id: str | None = Field(default=None, max_length=120)


def _tenant_settings(user_id: str) -> tuple[str, dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    return tenant_id, settings


def _resolve_maps_env_key() -> str:
    return (
        str(os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()
        or str(os.getenv("GOOGLE_PLACES_API_KEY", "")).strip()
        or str(os.getenv("GOOGLE_GEO_API_KEY", "")).strip()
    )


def _resolve_brave_env_key() -> str:
    return str(os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()


def _stored_secret(tenant_id: str, connector_id: str, key_name: str) -> str:
    record = get_credential_store().get(tenant_id=tenant_id, connector_id=connector_id)
    if record is None:
        return ""
    return str(record.values.get(key_name) or "").strip()


def _publish_event(
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


@router.get("/integrations/maps/status")
def maps_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    env_key = _resolve_maps_env_key()
    stored_key = _stored_secret(tenant_id, MAPS_CONNECTOR_ID, "GOOGLE_MAPS_API_KEY")
    source: str | None = None
    if env_key:
        source = "env"
    elif stored_key:
        source = "stored"
    return {
        "configured": bool(source),
        "source": source,
    }


@router.post("/integrations/maps/save")
def save_maps_integration_key(
    payload: MapsSaveRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    api_key = str(payload.api_key or "").strip()
    if len(api_key) < 16:
        raise HTTPException(
            status_code=400,
            detail={"code": "maps_api_key_invalid", "message": "Maps API key is invalid."},
        )
    tenant_id, _ = _tenant_settings(user_id)
    get_credential_store().set(
        tenant_id=tenant_id,
        connector_id=MAPS_CONNECTOR_ID,
        values={"GOOGLE_MAPS_API_KEY": api_key},
    )
    _publish_event(
        user_id=user_id,
        run_id=None,
        event_type="integrations.maps.saved",
        message="Maps API key saved to secure server store",
    )
    return {"status": "saved", "configured": True}


@router.post("/integrations/maps/clear")
def clear_maps_integration_key(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    deleted = get_credential_store().delete(tenant_id=tenant_id, connector_id=MAPS_CONNECTOR_ID)
    _publish_event(
        user_id=user_id,
        run_id=None,
        event_type="integrations.maps.cleared",
        message="Stored Maps API key cleared",
    )
    return {"status": "cleared", "cleared": bool(deleted)}


@router.get("/integrations/brave/status")
def brave_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    env_key = _resolve_brave_env_key()
    stored_key = _stored_secret(tenant_id, BRAVE_CONNECTOR_ID, "BRAVE_SEARCH_API_KEY")
    source: str | None = None
    if env_key:
        source = "env"
    elif stored_key:
        source = "stored"
    return {
        "configured": bool(source),
        "source": source,
    }


@router.post("/tools/web_search")
def run_web_search(
    payload: WebSearchRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    key = _resolve_brave_env_key() or _stored_secret(tenant_id, BRAVE_CONNECTOR_ID, "BRAVE_SEARCH_API_KEY")
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "brave_api_key_missing",
                "message": "BRAVE_SEARCH_API_KEY is not configured.",
            },
        )

    run_id = str(payload.run_id or "").strip() or None
    query = " ".join(str(payload.query or "").split())
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="status",
        message="Searching web...",
        data={"provider": "brave"},
    )
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="brave.search.query",
        message="Running Brave search query",
        data={"query": query, "domain": payload.domain or None},
    )

    try:
        service = BraveSearchService(api_key=key)
        if payload.domain:
            result = service.site_search(
                domain=payload.domain,
                query=query,
                count=payload.count,
                offset=payload.offset,
                country=payload.country,
                safesearch=payload.safesearch,
            )
        else:
            result = service.web_search(
                query=query,
                count=payload.count,
                offset=payload.offset,
                country=payload.country,
                safesearch=payload.safesearch,
            )
    except BraveSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "brave_search_failed",
                "message": "Brave search request failed.",
                "details": {"error": str(exc)},
            },
        ) from exc

    rows = result.get("results")
    results = rows if isinstance(rows, list) else []
    top_urls = [str(item.get("url") or "") for item in results if isinstance(item, dict)][:5]
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="brave.search.results",
        message=f"Brave search returned {len(results)} result(s)",
        data={"top_urls": top_urls},
    )
    return result
