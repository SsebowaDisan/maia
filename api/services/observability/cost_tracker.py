"""B5-02 — Cost tracking and budget limits.

Responsibility: real-time cost per tenant per day.  When the daily budget
limit is exceeded, new runs are blocked via ``assert_budget_ok``.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

# ── Pricing ────────────────────────────────────────────────────────────────────

_PRICING_PER_M: dict[str, dict[str, float]] = {
    "claude-opus-4-6":   {"in": 15.0,  "out": 75.0},
    "claude-sonnet-4-6": {"in": 3.0,   "out": 15.0},
    "claude-haiku-4-5":  {"in": 0.8,   "out": 4.0},
}
_DEFAULT_PRICING = {"in": 3.0, "out": 15.0}
_CU_STEP_COST = 0.005  # $0.005 per Computer Use step


class DailyCostRecord(SQLModel, table=True):
    __tablename__ = "maia_daily_cost"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    date_key: str = Field(index=True)  # "YYYY-MM-DD"
    total_cost_usd: float = 0.0
    llm_cost_usd: float = 0.0
    cu_cost_usd: float = 0.0


class BudgetLimit(SQLModel, table=True):
    __tablename__ = "maia_budget_limit"

    tenant_id: str = Field(primary_key=True)
    daily_limit_usd: float
    alert_threshold_fraction: float = 0.8  # alert at 80% of limit


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ─────────────────────────────────────────────────────────────────

def record_token_cost(
    tenant_id: str,
    agent_id: str,
    tokens_in: int,
    tokens_out: int,
    *,
    model: str = "claude-sonnet-4-6",
    computer_use_steps: int = 0,
) -> float:
    """Accumulate cost for a run.  Returns total USD charged."""
    _ensure_tables()
    pricing = _PRICING_PER_M.get(model, _DEFAULT_PRICING)
    llm_cost = (tokens_in / 1_000_000 * pricing["in"]) + (tokens_out / 1_000_000 * pricing["out"])
    cu_cost = computer_use_steps * _CU_STEP_COST
    total = llm_cost + cu_cost

    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _increment_daily(tenant_id, date_key, llm_cost=llm_cost, cu_cost=cu_cost)
    return round(total, 6)


def set_budget_limit(tenant_id: str, daily_limit_usd: float) -> None:
    _ensure_tables()
    with Session(engine) as session:
        existing = session.get(BudgetLimit, tenant_id)
        if existing:
            existing.daily_limit_usd = daily_limit_usd
            session.add(existing)
        else:
            session.add(BudgetLimit(tenant_id=tenant_id, daily_limit_usd=daily_limit_usd))
        session.commit()


def get_daily_cost(tenant_id: str, date_key: str | None = None) -> dict[str, Any]:
    date_key = date_key or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with Session(engine) as session:
        record = session.exec(
            select(DailyCostRecord)
            .where(DailyCostRecord.tenant_id == tenant_id)
            .where(DailyCostRecord.date_key == date_key)
        ).first()
    return {
        "tenant_id": tenant_id,
        "date_key": date_key,
        "total_cost_usd": record.total_cost_usd if record else 0.0,
        "llm_cost_usd": record.llm_cost_usd if record else 0.0,
        "cu_cost_usd": record.cu_cost_usd if record else 0.0,
    }


class BudgetExceededError(Exception):
    """Raised by assert_budget_ok when the daily limit is reached."""


def assert_budget_ok(tenant_id: str) -> None:
    """Raise BudgetExceededError if the daily limit is exceeded."""
    _ensure_tables()
    with Session(engine) as session:
        budget = session.get(BudgetLimit, tenant_id)
        if not budget:
            return  # No limit set → always OK

        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        record = session.exec(
            select(DailyCostRecord)
            .where(DailyCostRecord.tenant_id == tenant_id)
            .where(DailyCostRecord.date_key == date_key)
        ).first()
        spent = record.total_cost_usd if record else 0.0

        if spent >= budget.daily_limit_usd:
            raise BudgetExceededError(
                f"Daily budget limit of ${budget.daily_limit_usd:.2f} exceeded "
                f"(spent ${spent:.4f} today)."
            )


# ── Private ────────────────────────────────────────────────────────────────────

def _increment_daily(tenant_id: str, date_key: str, *, llm_cost: float, cu_cost: float) -> None:
    with Session(engine) as session:
        record = session.exec(
            select(DailyCostRecord)
            .where(DailyCostRecord.tenant_id == tenant_id)
            .where(DailyCostRecord.date_key == date_key)
        ).first()
        total = llm_cost + cu_cost
        if record:
            record.llm_cost_usd += llm_cost
            record.cu_cost_usd += cu_cost
            record.total_cost_usd += total
            session.add(record)
        else:
            session.add(DailyCostRecord(
                tenant_id=tenant_id,
                date_key=date_key,
                llm_cost_usd=llm_cost,
                cu_cost_usd=cu_cost,
                total_cost_usd=total,
            ))
        session.commit()
