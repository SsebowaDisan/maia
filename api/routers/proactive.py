"""P5-05 — Proactive insights REST endpoints.

Routes:
    GET  /api/insights              list insights (paginated, filterable)
    GET  /api/insights/count        unread badge count
    POST /api/insights/{id}/read    mark one insight read
    POST /api/insights/read-all     mark all insights read
    DELETE /api/insights/{id}       delete one insight
    POST /api/insights/trigger      manually fire one monitor cycle
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import get_current_user_id
from api.services.proactive.insight_store import (
    delete_insight,
    insight_to_dict,
    list_insights,
    mark_all_read,
    mark_read,
    unread_count,
)

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("", response_model=list[dict[str, Any]])
def get_insights(
    limit: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    rows = list_insights(user_id, limit=limit, unread_only=unread_only)
    return [insight_to_dict(r) for r in rows]


@router.get("/count")
def get_unread_count(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, int]:
    return {"unread": unread_count(user_id)}


@router.post("/{insight_id}/read")
def read_insight(
    insight_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, str]:
    if not mark_read(user_id, insight_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found.")
    return {"status": "ok"}


@router.post("/read-all")
def read_all_insights(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, int]:
    count = mark_all_read(user_id)
    return {"marked": count}


@router.delete("/{insight_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def remove_insight(
    insight_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    if not delete_insight(user_id, insight_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found.")


@router.post("/trigger")
def trigger_monitor(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    from api.services.proactive.monitor import get_proactive_monitor
    total = get_proactive_monitor().trigger_now(tenant_id=user_id)
    return {"signals_detected": total}
