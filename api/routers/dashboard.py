"""Dashboard Widgets API — pinnable agent output cards.

Users can pin agent/workflow outputs to a personal dashboard for at-a-glance monitoring.
Widgets auto-refresh based on the source agent's schedule.

Endpoints:
    GET  /api/dashboard                     — get user's dashboard widgets
    POST /api/dashboard                     — pin a new widget
    DELETE /api/dashboard/:widget_id        — remove a widget
    PATCH /api/dashboard/:widget_id         — update widget settings
    POST /api/dashboard/:widget_id/refresh  — manually refresh a widget
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _dashboard_path(user_id: str) -> Path:
    root = Path(".maia_agent") / "dashboards"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{user_id}.json"


def _load_widgets(user_id: str) -> list[dict[str, Any]]:
    fpath = _dashboard_path(user_id)
    if not fpath.exists():
        return []
    try:
        return json.loads(fpath.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_widgets(user_id: str, widgets: list[dict[str, Any]]) -> None:
    fpath = _dashboard_path(user_id)
    fpath.write_text(json.dumps(widgets, indent=2, default=str), encoding="utf-8")


class CreateWidgetRequest(BaseModel):
    title: str = Field(max_length=120)
    widget_type: str = Field(default="agent_output")
    source_agent_id: str = Field(default="")
    source_workflow_id: str = Field(default="")
    source_run_id: str = Field(default="")
    content: str = Field(default="")
    refresh_interval_minutes: int = Field(default=0, ge=0, le=1440)
    position: int = Field(default=0)


class UpdateWidgetRequest(BaseModel):
    title: str | None = None
    position: int | None = None
    refresh_interval_minutes: int | None = None


@router.get("")
def get_dashboard(user_id: str = Depends(get_current_user_id)) -> list[dict[str, Any]]:
    """Get all dashboard widgets for the current user."""
    return _load_widgets(user_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_widget(
    body: CreateWidgetRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Pin a new widget to the dashboard."""
    widget = {
        "id": uuid.uuid4().hex[:12],
        "title": body.title.strip(),
        "widget_type": body.widget_type,
        "source_agent_id": body.source_agent_id,
        "source_workflow_id": body.source_workflow_id,
        "source_run_id": body.source_run_id,
        "content": body.content[:5000],
        "refresh_interval_minutes": body.refresh_interval_minutes,
        "position": body.position,
        "created_at": time.time(),
        "last_refreshed_at": time.time(),
    }
    widgets = _load_widgets(user_id)
    widgets.append(widget)
    _save_widgets(user_id, widgets)
    return widget


@router.delete("/{widget_id}")
def delete_widget(
    widget_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Remove a widget from the dashboard."""
    widgets = _load_widgets(user_id)
    updated = [w for w in widgets if w.get("id") != widget_id]
    if len(updated) == len(widgets):
        raise HTTPException(status_code=404, detail="Widget not found.")
    _save_widgets(user_id, updated)
    return {"status": "deleted", "widget_id": widget_id}


@router.patch("/{widget_id}")
def update_widget(
    widget_id: str,
    body: UpdateWidgetRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Update widget settings (title, position, refresh interval)."""
    widgets = _load_widgets(user_id)
    target = next((w for w in widgets if w.get("id") == widget_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Widget not found.")
    if body.title is not None:
        target["title"] = body.title.strip()[:120]
    if body.position is not None:
        target["position"] = body.position
    if body.refresh_interval_minutes is not None:
        target["refresh_interval_minutes"] = max(0, min(1440, body.refresh_interval_minutes))
    _save_widgets(user_id, widgets)
    return target


@router.post("/{widget_id}/refresh")
def refresh_widget(
    widget_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Manually refresh a widget by re-running its source agent/workflow."""
    widgets = _load_widgets(user_id)
    target = next((w for w in widgets if w.get("id") == widget_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Widget not found.")

    # Re-run the source and update content
    new_content = ""
    agent_id = target.get("source_agent_id", "")
    workflow_id = target.get("source_workflow_id", "")

    if agent_id:
        try:
            from api.services.agents.runner import run_agent_task
            parts = []
            for chunk in run_agent_task(f"Refresh dashboard widget: {target.get('title', '')}", tenant_id=user_id):
                text = chunk.get("text") or chunk.get("content") or ""
                if text:
                    parts.append(str(text))
            new_content = "".join(parts)[:5000]
        except Exception as exc:
            new_content = f"Refresh failed: {exc}"

    if new_content:
        target["content"] = new_content
        target["last_refreshed_at"] = time.time()
        _save_widgets(user_id, widgets)

    return target
