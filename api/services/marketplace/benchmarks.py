"""B6-04 — Cross-tenant agent benchmarking (opt-in).

Responsibility: aggregate anonymous performance signals from opt-in tenants.
No prompts, outputs, or company data shared — only numeric metrics.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


class BenchmarkOptIn(SQLModel, table=True):
    __tablename__ = "maia_benchmark_opt_in"

    tenant_id: str = Field(primary_key=True)
    opted_in_at: float = Field(default_factory=time.time)


class BenchmarkSignal(SQLModel, table=True):
    __tablename__ = "maia_benchmark_signal"

    id: Optional[int] = Field(default=None, primary_key=True)
    marketplace_agent_id: str = Field(index=True)
    # Anonymised — no tenant_id stored in aggregate signals
    task_completed: bool
    quality_score: float  # 0.0–1.0 (from feedback / approval)
    cost_usd: float
    computer_use_steps: int
    recorded_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def opt_in_benchmarking(tenant_id: str) -> None:
    _ensure_tables()
    with Session(engine) as session:
        if not session.get(BenchmarkOptIn, tenant_id):
            session.add(BenchmarkOptIn(tenant_id=tenant_id))
            session.commit()


def opt_out_benchmarking(tenant_id: str) -> None:
    with Session(engine) as session:
        record = session.get(BenchmarkOptIn, tenant_id)
        if record:
            session.delete(record)
            session.commit()


def is_opted_in(tenant_id: str) -> bool:
    with Session(engine) as session:
        return session.get(BenchmarkOptIn, tenant_id) is not None


def submit_signal(
    tenant_id: str,
    marketplace_agent_id: str,
    *,
    task_completed: bool,
    quality_score: float,
    cost_usd: float,
    computer_use_steps: int = 0,
) -> None:
    """Submit a run signal if the tenant is opted in."""
    _ensure_tables()
    if not is_opted_in(tenant_id):
        return
    signal = BenchmarkSignal(
        marketplace_agent_id=marketplace_agent_id,
        task_completed=task_completed,
        quality_score=max(0.0, min(1.0, quality_score)),
        cost_usd=cost_usd,
        computer_use_steps=computer_use_steps,
    )
    with Session(engine) as session:
        session.add(signal)
        session.commit()


def get_benchmark(marketplace_agent_id: str) -> dict[str, Any]:
    """Return aggregate benchmark for a marketplace agent."""
    with Session(engine) as session:
        signals = session.exec(
            select(BenchmarkSignal)
            .where(BenchmarkSignal.marketplace_agent_id == marketplace_agent_id)
        ).all()

    if not signals:
        return {
            "marketplace_agent_id": marketplace_agent_id,
            "sample_count": 0,
            "task_completion_rate": None,
            "avg_quality_score": None,
            "avg_cost_usd": None,
            "avg_computer_use_steps": None,
        }

    n = len(signals)
    completed = sum(1 for s in signals if s.task_completed)
    return {
        "marketplace_agent_id": marketplace_agent_id,
        "sample_count": n,
        "task_completion_rate": round(completed / n, 4),
        "avg_quality_score": round(sum(s.quality_score for s in signals) / n, 4),
        "avg_cost_usd": round(sum(s.cost_usd for s in signals) / n, 6),
        "avg_computer_use_steps": round(sum(s.computer_use_steps for s in signals) / n, 2),
    }
