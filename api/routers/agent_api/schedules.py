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
    frequency = str(payload.frequency or "weekly").strip()

    # Accept both legacy frequencies and cron expressions
    _LEGACY_TO_CRON = {"daily": "0 9 * * *", "weekly": "0 9 * * 1", "monthly": "0 9 1 * *"}
    cron_expression = _LEGACY_TO_CRON.get(frequency, frequency)

    # Validate cron format (5 fields)
    parts = cron_expression.split()
    if len(parts) != 5:
        raise HTTPException(status_code=400, detail="frequency must be a cron expression (5 fields) or one of: daily, weekly, monthly")

    # Try modern AgentScheduler first (supports full cron)
    try:
        from api.services.agents.scheduler import get_agent_scheduler
        scheduler = get_agent_scheduler()
        result = scheduler.register_schedule(
            tenant_id=user_id,
            agent_id=payload.prompt,  # workflow run ID stored as agent_id
            cron_expression=cron_expression,
        )
        return {
            "id": str(result.get("id", "")),
            "name": payload.name,
            "frequency": frequency,
            "cron_expression": cron_expression,
            "enabled": True,
            "status": "scheduled",
        }
    except Exception:
        pass

    # Fallback to legacy report scheduler
    legacy_freq = frequency if frequency in {"daily", "weekly", "monthly"} else "weekly"
    return get_report_scheduler().create(
        user_id=user_id,
        name=payload.name,
        prompt=payload.prompt,
        frequency=legacy_freq,  # type: ignore[arg-type]
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
