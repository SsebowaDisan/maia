from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.services.agent.report_scheduler import get_report_scheduler

from .schemas import ScheduleCreateRequest, ScheduleToggleRequest

router = APIRouter(tags=["agent"])


@router.get("/schedules")
def list_schedules(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    return get_report_scheduler().list(user_id=user_id)


@router.post("/schedules")
def create_schedule(
    payload: ScheduleCreateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    if payload.frequency not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="frequency must be one of: daily, weekly, monthly")
    return get_report_scheduler().create(
        user_id=user_id,
        name=payload.name,
        prompt=payload.prompt,
        frequency=payload.frequency,  # type: ignore[arg-type]
        outputs=payload.outputs,
        channels=payload.channels,
    )


@router.post("/schedules/{schedule_id}/trigger")
def trigger_schedule_now(
    schedule_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    try:
        return get_report_scheduler().trigger_now(user_id=user_id, schedule_id=schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/schedules/{schedule_id}")
def toggle_schedule(
    schedule_id: str,
    payload: ScheduleToggleRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    try:
        return get_report_scheduler().toggle(
            user_id=user_id,
            schedule_id=schedule_id,
            enabled=payload.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    try:
        get_report_scheduler().delete(user_id=user_id, schedule_id=schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "schedule_id": schedule_id}
