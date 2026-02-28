from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.auth import get_current_user_id
from api.services.agent.memory import get_memory_service

from .schemas import PlaybookCreateRequest, PlaybookPatchRequest

router = APIRouter(tags=["agent"])


@router.get("/playbooks")
def list_playbooks(limit: int = 50) -> list[dict[str, Any]]:
    return get_memory_service().list_playbooks(limit=limit)


@router.post("/playbooks")
def create_playbook(
    payload: PlaybookCreateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return get_memory_service().save_playbook(
        name=payload.name,
        prompt_template=payload.prompt_template,
        tool_ids=payload.tool_ids,
        owner_id=user_id,
    )


@router.patch("/playbooks/{playbook_id}")
def patch_playbook(
    playbook_id: str,
    payload: PlaybookPatchRequest,
) -> dict[str, Any]:
    patch = payload.model_dump(exclude_none=True)
    return get_memory_service().update_playbook(playbook_id, patch)
