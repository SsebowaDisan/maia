"""P10-03 — Observability / ROI REST endpoints.

Routes:
    GET  /api/roi                     — ROI summary for the calling tenant
    GET  /api/roi/config              — per-agent ROI configs
    PATCH /api/agents/{id}/roi-config — set estimated_minutes_per_run for an agent
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.auth import get_current_user_id

router = APIRouter(tags=["observability"])


class RoiConfigRequest(BaseModel):
    estimated_minutes_per_run: float
    hourly_rate_usd: float = 50.0


@router.get("/api/roi")
def get_roi(
    days: int = Query(default=30, ge=1, le=365),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return aggregate and per-agent ROI for the last N days."""
    from api.services.observability.roi_tracker import get_roi_summary
    return get_roi_summary(user_id, days=days)


@router.patch("/api/agents/{agent_id}/roi-config")
def set_agent_roi_config(
    agent_id: str,
    body: RoiConfigRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Configure the estimated minutes saved per run for ROI calculation."""
    from api.services.observability.roi_tracker import set_roi_config
    set_roi_config(
        user_id,
        agent_id,
        estimated_minutes_per_run=body.estimated_minutes_per_run,
        hourly_rate_usd=body.hourly_rate_usd,
    )
    return {
        "agent_id": agent_id,
        "estimated_minutes_per_run": body.estimated_minutes_per_run,
        "hourly_rate_usd": body.hourly_rate_usd,
    }
