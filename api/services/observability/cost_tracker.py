"""B5-02 - Cost tracking and budget limits."""
from __future__ import annotations

import logging as _logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine
from api.services.observability.model_pricing import calculate_token_cost_usd

_CU_STEP_COST = 0.005  # $0.005 per Computer Use step


class DailyCostRecord(SQLModel, table=True):
    __tablename__ = "maia_daily_cost"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    date_key: str = Field(index=True)  # YYYY-MM-DD
    total_cost_usd: float = 0.0
    llm_cost_usd: float = 0.0
    cu_cost_usd: float = 0.0


class BudgetLimit(SQLModel, table=True):
    __tablename__ = "maia_budget_limit"

    tenant_id: str = Field(primary_key=True)
    daily_limit_usd: float
    alert_threshold_fraction: float = 0.8


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def record_token_cost(
    tenant_id: str,
    agent_id: str,
    tokens_in: int,
    tokens_out: int,
    *,
    model: str = "claude-sonnet-4-6",
    computer_use_steps: int = 0,
) -> float:
    """Accumulate cost for a run. Returns total USD charged."""
    _ensure_tables()
    llm_cost = calculate_token_cost_usd(model=model, tokens_in=tokens_in, tokens_out=tokens_out)
    cu_cost = computer_use_steps * _CU_STEP_COST
    total = llm_cost + cu_cost

    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _increment_daily(tenant_id, date_key, llm_cost=llm_cost, cu_cost=cu_cost)
    _check_budget_alert(tenant_id, date_key)
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
            return

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


_logger = _logging.getLogger(__name__)


def _check_budget_alert(tenant_id: str, date_key: str) -> None:
    """Emit a structured warning when spending crosses threshold."""
    try:
        with Session(engine) as session:
            budget = session.get(BudgetLimit, tenant_id)
            if not budget:
                return
            record = session.exec(
                select(DailyCostRecord)
                .where(DailyCostRecord.tenant_id == tenant_id)
                .where(DailyCostRecord.date_key == date_key)
            ).first()
        if not record:
            return

        spent = record.total_cost_usd
        threshold = budget.daily_limit_usd * budget.alert_threshold_fraction
        if spent >= threshold:
            pct = spent / budget.daily_limit_usd * 100
            _logger.warning(
                "BUDGET_ALERT tenant=%s spent=$%.4f (%.1f%% of $%.2f daily limit)",
                tenant_id,
                spent,
                pct,
                budget.daily_limit_usd,
            )
    except Exception:
        pass


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
            session.add(
                DailyCostRecord(
                    tenant_id=tenant_id,
                    date_key=date_key,
                    llm_cost_usd=llm_cost,
                    cu_cost_usd=cu_cost,
                    total_cost_usd=total,
                )
            )
        session.commit()
