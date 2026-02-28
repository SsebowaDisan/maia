from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.services.agent.auth.credentials import get_credential_store

from .common import (
    MAPS_CONNECTOR_ID,
    publish_event,
    resolve_maps_env_key,
    stored_secret,
    tenant_settings,
)
from .schemas import MapsSaveRequest

router = APIRouter(tags=["agent-integrations"])


@router.get("/integrations/maps/status")
def maps_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = tenant_settings(user_id)
    env_key = resolve_maps_env_key()
    stored_key = stored_secret(tenant_id, MAPS_CONNECTOR_ID, "GOOGLE_MAPS_API_KEY")
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
    tenant_id, _ = tenant_settings(user_id)
    get_credential_store().set(
        tenant_id=tenant_id,
        connector_id=MAPS_CONNECTOR_ID,
        values={"GOOGLE_MAPS_API_KEY": api_key},
    )
    publish_event(
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
    tenant_id, _ = tenant_settings(user_id)
    deleted = get_credential_store().delete(tenant_id=tenant_id, connector_id=MAPS_CONNECTOR_ID)
    publish_event(
        user_id=user_id,
        run_id=None,
        event_type="integrations.maps.cleared",
        message="Stored Maps API key cleared",
    )
    return {"status": "cleared", "cleared": bool(deleted)}
