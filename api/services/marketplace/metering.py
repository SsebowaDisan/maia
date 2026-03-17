"""B3-05 - Usage metering."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine
from api.services.observability.model_pricing import calculate_token_cost_usd

_COMPUTER_USE_STEP_COST_USD = 0.005  # $0.005 per Computer Use step (approx)


class UsageRecord(SQLModel, table=True):
    __tablename__ = "maia_usage_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    run_id: str = Field(index=True)
    date_key: str  # YYYY-MM-DD for daily aggregation
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls: int = 0
    computer_use_steps: int = 0
    duration_ms: int = 0
    recorded_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def record_usage(
    tenant_id: str,
    agent_id: str,
    run_id: str,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tool_calls: int = 0,
    computer_use_steps: int = 0,
    duration_ms: int = 0,
) -> None:
    """Persist a usage record for one agent run."""
    _ensure_tables()
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    record = UsageRecord(
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_id=run_id,
        date_key=date_key,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tool_calls=tool_calls,
        computer_use_steps=computer_use_steps,
        duration_ms=duration_ms,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()

    try:
        from api.services.observability.roi_tracker import record_roi_event

        record_roi_event(tenant_id, agent_id, date_key)
    except Exception:
        pass


def get_usage_summary(
    tenant_id: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Return aggregated usage for a tenant over a date range."""
    with Session(engine) as session:
        q = select(UsageRecord).where(UsageRecord.tenant_id == tenant_id)
        if agent_id:
            q = q.where(UsageRecord.agent_id == agent_id)
        if start_date:
            q = q.where(UsageRecord.date_key >= start_date)
        if end_date:
            q = q.where(UsageRecord.date_key <= end_date)
        records = session.exec(q).all()

    totals: dict[str, Any] = {
        "tokens_in": 0,
        "tokens_out": 0,
        "tool_calls": 0,
        "computer_use_steps": 0,
        "duration_ms": 0,
        "run_count": len(records),
    }
    by_agent: dict[str, dict[str, int]] = {}

    for record in records:
        totals["tokens_in"] += record.tokens_in
        totals["tokens_out"] += record.tokens_out
        totals["tool_calls"] += record.tool_calls
        totals["computer_use_steps"] += record.computer_use_steps
        totals["duration_ms"] += record.duration_ms

        agg = by_agent.setdefault(
            record.agent_id,
            {
                "tokens_in": 0,
                "tokens_out": 0,
                "tool_calls": 0,
                "computer_use_steps": 0,
                "run_count": 0,
            },
        )
        agg["tokens_in"] += record.tokens_in
        agg["tokens_out"] += record.tokens_out
        agg["tool_calls"] += record.tool_calls
        agg["computer_use_steps"] += record.computer_use_steps
        agg["run_count"] += 1

    totals["by_agent"] = by_agent
    return totals


def calculate_charges(
    tenant_id: str,
    billing_period_start: str,
    billing_period_end: str,
    model: str = "claude-sonnet-4-6",
) -> dict[str, Any]:
    """Calculate approximate charges for a billing period."""
    summary = get_usage_summary(
        tenant_id,
        start_date=billing_period_start,
        end_date=billing_period_end,
    )
    llm_cost = calculate_token_cost_usd(
        model=model,
        tokens_in=summary["tokens_in"],
        tokens_out=summary["tokens_out"],
    )
    cu_cost = summary["computer_use_steps"] * _COMPUTER_USE_STEP_COST_USD
    return {
        "billing_period": f"{billing_period_start} to {billing_period_end}",
        "llm_cost_usd": round(llm_cost, 4),
        "computer_use_cost_usd": round(cu_cost, 4),
        "total_cost_usd": round(llm_cost + cu_cost, 4),
        "usage": summary,
    }
