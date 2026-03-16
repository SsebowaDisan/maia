"""P10-01 — ROI / Savings tracker.

Responsibility: accumulate per-agent run completions and estimate the time and
cost saved for each tenant.

Formula
-------
  time_saved_minutes  = estimated_minutes_per_run × runs_completed
  cost_avoided_usd    = time_saved_minutes × (hourly_rate_usd / 60)

The ``hourly_rate_usd`` defaults to $50/hr and is configurable per tenant via
the BudgetLimit table (extending it with an optional hourly_rate column).

ROI records are written from ``record_usage()`` in metering.py by calling
``record_roi_event()``.  A separate ``AgentRoiConfig`` table stores the
estimated minutes per run for each agent.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

_DEFAULT_HOURLY_RATE_USD = 50.0


# ── ORM ───────────────────────────────────────────────────────────────────────

class AgentRoiConfig(SQLModel, table=True):
    """Per-agent ROI configuration — estimated minutes saved per run."""
    __tablename__ = "maia_agent_roi_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    estimated_minutes_per_run: float = 0.0
    hourly_rate_usd: float = _DEFAULT_HOURLY_RATE_USD


class AgentRoiRecord(SQLModel, table=True):
    """Cumulative ROI accumulator per (tenant, agent, date)."""
    __tablename__ = "maia_agent_roi"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    date_key: str = Field(index=True)   # "YYYY-MM-DD"
    runs_completed: int = 0
    time_saved_minutes: float = 0.0
    cost_avoided_usd: float = 0.0


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ─────────────────────────────────────────────────────────────────

def set_roi_config(
    tenant_id: str,
    agent_id: str,
    estimated_minutes_per_run: float,
    hourly_rate_usd: float = _DEFAULT_HOURLY_RATE_USD,
) -> None:
    """Store or update the ROI configuration for an agent."""
    _ensure_tables()
    with Session(engine) as session:
        existing = session.exec(
            select(AgentRoiConfig)
            .where(AgentRoiConfig.tenant_id == tenant_id)
            .where(AgentRoiConfig.agent_id == agent_id)
        ).first()
        if existing:
            existing.estimated_minutes_per_run = estimated_minutes_per_run
            existing.hourly_rate_usd = hourly_rate_usd
            session.add(existing)
        else:
            session.add(AgentRoiConfig(
                tenant_id=tenant_id,
                agent_id=agent_id,
                estimated_minutes_per_run=estimated_minutes_per_run,
                hourly_rate_usd=hourly_rate_usd,
            ))
        session.commit()


def record_roi_event(tenant_id: str, agent_id: str, date_key: str) -> None:
    """Record one completed run and accumulate ROI for (tenant, agent, date)."""
    _ensure_tables()
    with Session(engine) as session:
        config = session.exec(
            select(AgentRoiConfig)
            .where(AgentRoiConfig.tenant_id == tenant_id)
            .where(AgentRoiConfig.agent_id == agent_id)
        ).first()

        minutes = config.estimated_minutes_per_run if config else 0.0
        rate = config.hourly_rate_usd if config else _DEFAULT_HOURLY_RATE_USD
        cost_avoided = minutes * (rate / 60.0)

        record = session.exec(
            select(AgentRoiRecord)
            .where(AgentRoiRecord.tenant_id == tenant_id)
            .where(AgentRoiRecord.agent_id == agent_id)
            .where(AgentRoiRecord.date_key == date_key)
        ).first()

        if record:
            record.runs_completed += 1
            record.time_saved_minutes += minutes
            record.cost_avoided_usd += cost_avoided
            session.add(record)
        else:
            session.add(AgentRoiRecord(
                tenant_id=tenant_id,
                agent_id=agent_id,
                date_key=date_key,
                runs_completed=1,
                time_saved_minutes=minutes,
                cost_avoided_usd=cost_avoided,
            ))
        session.commit()


def get_roi_summary(
    tenant_id: str,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Return aggregate + per-agent ROI for the last N days."""
    _ensure_tables()
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    with Session(engine) as session:
        rows = session.exec(
            select(AgentRoiRecord)
            .where(AgentRoiRecord.tenant_id == tenant_id)
            .where(AgentRoiRecord.date_key >= cutoff)
        ).all()

    by_agent: dict[str, dict[str, Any]] = {}
    total_runs = 0
    total_minutes = 0.0
    total_cost_avoided = 0.0

    for row in rows:
        agg = by_agent.setdefault(row.agent_id, {
            "agent_id": row.agent_id,
            "runs_completed": 0,
            "time_saved_minutes": 0.0,
            "cost_avoided_usd": 0.0,
        })
        agg["runs_completed"] += row.runs_completed
        agg["time_saved_minutes"] += row.time_saved_minutes
        agg["cost_avoided_usd"] += row.cost_avoided_usd
        total_runs += row.runs_completed
        total_minutes += row.time_saved_minutes
        total_cost_avoided += row.cost_avoided_usd

    return {
        "tenant_id": tenant_id,
        "period_days": days,
        "total_runs_completed": total_runs,
        "total_time_saved_hours": round(total_minutes / 60.0, 2),
        "total_cost_avoided_usd": round(total_cost_avoided, 2),
        "by_agent": sorted(
            by_agent.values(),
            key=lambda x: x["cost_avoided_usd"],
            reverse=True,
        ),
    }
