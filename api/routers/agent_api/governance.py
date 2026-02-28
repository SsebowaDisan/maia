from __future__ import annotations

from fastapi import APIRouter

from api.services.agent.governance import get_governance_service

from .schemas import GovernancePatchRequest

router = APIRouter(tags=["agent"])


@router.get("/governance")
def get_governance() -> dict[str, object]:
    return get_governance_service().get()


@router.patch("/governance")
def patch_governance(payload: GovernancePatchRequest) -> dict[str, object]:
    service = get_governance_service()
    result = service.get()
    if payload.global_kill_switch is not None:
        result = service.set_global_kill_switch(payload.global_kill_switch)
    if payload.tool_id and payload.tool_enabled is not None:
        result = service.set_tool_enabled(payload.tool_id, payload.tool_enabled)
    return result
