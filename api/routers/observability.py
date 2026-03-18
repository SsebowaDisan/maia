"""P10-03 — Observability / ROI REST endpoints.

Routes:
    GET  /api/roi                          — ROI summary for the calling tenant
    PATCH /api/agents/{id}/roi-config      — set estimated_minutes_per_run for an agent
    GET  /api/observability/timeline       — unified run timeline across agents+workflows
    GET  /api/observability/cost           — daily cost summary
"""
from __future__ import annotations

import time
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


# ── Unified run timeline ──────────────────────────────────────────────────────

@router.get("/api/observability/timeline")
def get_run_timeline(
    user_id: str = Depends(get_current_user_id),
    status: str | None = Query(default=None),
    trigger_type: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    since: float | None = Query(default=None),
    until: float | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Return a unified timeline of agent runs + workflow runs."""
    from api.services.observability.telemetry import query_runs
    from api.services.agents.workflow_run_store import list_runs as list_workflow_runs

    entries: list[dict[str, Any]] = []

    # ── Agent / scheduled / event runs from telemetry ─────────────────────
    try:
        telemetry_runs = query_runs(
            tenant_id=user_id,
            status=status,
            trigger_type=trigger_type,
            start_after=since,
            end_before=until,
            limit=limit,
        )
        for r in telemetry_runs:
            run_type = "agent_run"
            if r.trigger_type == "scheduled":
                run_type = "scheduled_run"
            elif r.trigger_type == "event":
                run_type = "event_run"

            if type and run_type != type:
                continue

            entries.append({
                "id": r.run_id,
                "type": run_type,
                "name": r.agent_id,
                "agent_id": r.agent_id,
                "status": r.status,
                "trigger": r.trigger_type,
                "started_at": r.started_at,
                "ended_at": r.ended_at,
                "duration_ms": int((r.ended_at - r.started_at) * 1000) if r.ended_at else None,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "tool_calls": len(
                    __import__("json").loads(r.tool_calls_json)
                ) if r.tool_calls_json and r.tool_calls_json != "[]" else 0,
                "error": r.error,
            })
    except Exception:
        pass

    # ── Workflow runs ─────────────────────────────────────────────────────
    if not type or type == "workflow_run":
        try:
            wf_runs = list_workflow_runs(user_id)
            for wr in wf_runs:
                if status and wr.get("status") != status:
                    continue
                started = wr.get("started_at", 0)
                if since and started < since:
                    continue
                if until and started > until:
                    continue

                entries.append({
                    "id": wr.get("run_id", ""),
                    "type": "workflow_run",
                    "name": wr.get("workflow_id", "workflow"),
                    "workflow_id": wr.get("workflow_id"),
                    "status": wr.get("status", "unknown"),
                    "trigger": "manual",
                    "started_at": started,
                    "ended_at": wr.get("completed_at"),
                    "duration_ms": wr.get("duration_ms"),
                    "step_count": len(wr.get("step_results", [])),
                    "steps_completed": sum(
                        1 for s in wr.get("step_results", [])
                        if s.get("status") == "completed"
                    ),
                    "error": wr.get("error"),
                })
        except Exception:
            pass

    # Sort by started_at descending, limit
    entries.sort(key=lambda e: e.get("started_at", 0), reverse=True)
    return entries[:limit]


@router.get("/api/observability/cost")
def get_cost_summary(
    user_id: str = Depends(get_current_user_id),
    days: int = Query(default=7, ge=1, le=90),
) -> dict[str, Any]:
    """Return daily cost breakdown for the last N days."""
    import datetime as _dt
    from api.services.observability.cost_tracker import get_daily_cost
    costs = []
    try:
        today = _dt.date.today()
        for i in range(days):
            day = today - _dt.timedelta(days=i)
            day_key = day.isoformat()
            cost = get_daily_cost(user_id, date_key=day_key)
            if cost:
                costs.append(cost)
    except Exception:
        pass
    return {"tenant_id": user_id, "days": days, "daily_costs": costs}


# ── Budget settings ──────────────────────────────────────────────────────────

class BudgetSettingsRequest(BaseModel):
    daily_limit_usd: float
    alert_threshold_fraction: float = 0.8


@router.get("/api/observability/budget")
def get_budget(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return the current budget limit + today's spend."""
    from api.services.observability.cost_tracker import get_daily_cost
    import datetime as _dt
    try:
        from sqlmodel import Session
        from ktem.db.engine import engine
        from api.services.observability.cost_tracker import BudgetLimit, _ensure_tables
        _ensure_tables()
        with Session(engine) as session:
            budget = session.get(BudgetLimit, user_id)
        daily_limit_usd = budget.daily_limit_usd if budget else 0.0
        alert_threshold_fraction = budget.alert_threshold_fraction if budget else 0.8
    except Exception:
        daily_limit_usd = 0.0
        alert_threshold_fraction = 0.8

    today_key = _dt.date.today().isoformat()
    today_cost = get_daily_cost(user_id, date_key=today_key)
    return {
        "daily_limit_usd": daily_limit_usd,
        "alert_threshold_fraction": alert_threshold_fraction,
        "today_cost_usd": today_cost.get("total_cost_usd", 0.0) if today_cost else 0.0,
        "today_llm_cost_usd": today_cost.get("llm_cost_usd", 0.0) if today_cost else 0.0,
        "today_cu_cost_usd": today_cost.get("cu_cost_usd", 0.0) if today_cost else 0.0,
    }


@router.put("/api/observability/budget")
def set_budget(
    body: BudgetSettingsRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Set/update the daily budget limit."""
    from api.services.observability.cost_tracker import set_budget_limit
    try:
        from sqlmodel import Session
        from ktem.db.engine import engine
        from api.services.observability.cost_tracker import BudgetLimit, _ensure_tables
        _ensure_tables()
        with Session(engine) as session:
            existing = session.get(BudgetLimit, user_id)
            if existing:
                existing.daily_limit_usd = body.daily_limit_usd
                existing.alert_threshold_fraction = body.alert_threshold_fraction
                session.add(existing)
            else:
                session.add(BudgetLimit(
                    tenant_id=user_id,
                    daily_limit_usd=body.daily_limit_usd,
                    alert_threshold_fraction=body.alert_threshold_fraction,
                ))
            session.commit()
    except Exception:
        set_budget_limit(user_id, body.daily_limit_usd)
    return {
        "daily_limit_usd": body.daily_limit_usd,
        "alert_threshold_fraction": body.alert_threshold_fraction,
    }
