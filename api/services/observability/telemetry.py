"""B5-01 — Run telemetry store.

Responsibility: persist structured telemetry per agent run and provide
queryable aggregates.  Tool calls, gate events, Computer Use steps, and
errors are all captured.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

RunStatus = Literal["completed", "failed", "cancelled", "running"]
TriggerType = Literal["manual", "scheduled", "event"]


class RunTelemetry(SQLModel, table=True):
    __tablename__ = "maia_run_telemetry"

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    agent_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    trigger_type: TriggerType = "manual"
    started_at: float = Field(default_factory=time.time)
    ended_at: Optional[float] = None
    status: RunStatus = "running"
    tokens_in: int = 0
    tokens_out: int = 0
    tool_calls_json: str = "[]"        # list[{tool_id, latency_ms, success}]
    gate_events_json: str = "[]"       # list[{gate_id, decision, latency_ms}]
    computer_use_steps: int = 0
    computer_use_session_id: Optional[str] = None
    error: Optional[str] = None


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def record_run_start(
    run_id: str,
    agent_id: str,
    tenant_id: str,
    trigger_type: str = "manual",
) -> RunTelemetry:
    _ensure_tables()
    record = RunTelemetry(
        run_id=run_id,
        agent_id=agent_id,
        tenant_id=tenant_id,
        trigger_type=trigger_type,  # type: ignore[arg-type]
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def record_run_end(
    run_id: str,
    *,
    status: RunStatus,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tool_calls: list[dict[str, Any]] | None = None,
    gate_events: list[dict[str, Any]] | None = None,
    computer_use_steps: int = 0,
    computer_use_session_id: str | None = None,
    error: str | None = None,
) -> None:
    with Session(engine) as session:
        record = session.get(RunTelemetry, run_id)
        if record:
            record.ended_at = time.time()
            record.status = status
            record.tokens_in = tokens_in
            record.tokens_out = tokens_out
            record.tool_calls_json = json.dumps(tool_calls or [])
            record.gate_events_json = json.dumps(gate_events or [])
            record.computer_use_steps = computer_use_steps
            record.computer_use_session_id = computer_use_session_id
            record.error = error
            session.add(record)
            session.commit()


def get_run(run_id: str) -> Optional[RunTelemetry]:
    with Session(engine) as session:
        return session.get(RunTelemetry, run_id)


def query_runs(
    tenant_id: str,
    *,
    agent_id: str | None = None,
    status: RunStatus | None = None,
    trigger_type: TriggerType | None = None,
    start_after: float | None = None,
    end_before: float | None = None,
    limit: int = 50,
) -> Sequence[RunTelemetry]:
    with Session(engine) as session:
        q = select(RunTelemetry).where(RunTelemetry.tenant_id == tenant_id)
        if agent_id:
            q = q.where(RunTelemetry.agent_id == agent_id)
        if status:
            q = q.where(RunTelemetry.status == status)
        if trigger_type:
            q = q.where(RunTelemetry.trigger_type == trigger_type)
        if start_after:
            q = q.where(RunTelemetry.started_at >= start_after)
        if end_before:
            q = q.where(RunTelemetry.started_at <= end_before)
        return session.exec(q.order_by(RunTelemetry.started_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]


def aggregate_runs(
    tenant_id: str,
    *,
    agent_id: str | None = None,
    start_after: float | None = None,
    end_before: float | None = None,
) -> dict[str, Any]:
    """Return aggregate metrics across matched runs."""
    runs = query_runs(
        tenant_id,
        agent_id=agent_id,
        start_after=start_after,
        end_before=end_before,
        limit=10_000,
    )
    totals: dict[str, Any] = {
        "run_count": len(runs),
        "tokens_in": 0,
        "tokens_out": 0,
        "computer_use_steps": 0,
        "tool_call_count": 0,
        "gate_event_count": 0,
        "status_distribution": {},
        "by_agent": {},
    }
    for r in runs:
        totals["tokens_in"] += r.tokens_in
        totals["tokens_out"] += r.tokens_out
        totals["computer_use_steps"] += r.computer_use_steps
        try:
            totals["tool_call_count"] += len(json.loads(r.tool_calls_json))
            totals["gate_event_count"] += len(json.loads(r.gate_events_json))
        except Exception:
            pass
        totals["status_distribution"][r.status] = totals["status_distribution"].get(r.status, 0) + 1

        agg = totals["by_agent"].setdefault(r.agent_id, {
            "run_count": 0, "tokens_in": 0, "tokens_out": 0, "computer_use_steps": 0,
        })
        agg["run_count"] += 1
        agg["tokens_in"] += r.tokens_in
        agg["tokens_out"] += r.tokens_out
        agg["computer_use_steps"] += r.computer_use_steps
    return totals
