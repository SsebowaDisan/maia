"""P5-01 — Signal detector.

Responsibility: run registered check functions against connector data and emit
SignalEvent objects when thresholds or anomalies are detected.

Usage:
    detector = SignalDetector()
    detector.register_check("my_check", my_check_fn)
    signals = detector.run_checks(tenant_id)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import logging

logger = logging.getLogger(__name__)


@dataclass
class SignalEvent:
    tenant_id: str
    signal_type: str
    severity: str            # "info" | "warning" | "critical"
    title: str
    summary: str = ""
    source_ref: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = field(default_factory=time.time)


# ── Check function type ────────────────────────────────────────────────────────

CheckFn = Callable[[str], list[SignalEvent]]
"""A check function receives a tenant_id and returns a (possibly empty) list of
SignalEvent objects.  It must not raise; exceptions are caught and logged."""


# ── Built-in checks ────────────────────────────────────────────────────────────

def _check_overdue_agents(tenant_id: str) -> list[SignalEvent]:
    """Detect scheduled agents that missed their last run by >2× their period."""
    signals: list[SignalEvent] = []
    try:
        from api.services.agents.scheduler import get_agent_scheduler
        scheduler = get_agent_scheduler()
        schedules = scheduler.list_schedules(tenant_id)
        import time as _time
        now = _time.time()
        for s in schedules:
            if not s.get("enabled"):
                continue
            last_run = s.get("last_run_at")
            next_run_str = s.get("next_run_at") or ""
            if not last_run or not next_run_str:
                continue
            # Parse next_run_at as ISO string
            from datetime import datetime, timezone
            try:
                next_run_dt = datetime.fromisoformat(next_run_str)
                next_run_ts = next_run_dt.timestamp()
            except ValueError:
                continue
            if now > next_run_ts + 3600:  # overdue by >1 hour
                signals.append(SignalEvent(
                    tenant_id=tenant_id,
                    signal_type="overdue_agent",
                    severity="warning",
                    title=f"Scheduled agent overdue: {s.get('name', s.get('agent_id', '?'))}",
                    summary=(
                        f"Agent '{s.get('name', s.get('agent_id', '?'))}' was due at "
                        f"{next_run_str} but has not run yet."
                    ),
                    source_ref=str(s.get("agent_id") or ""),
                    payload={"schedule": s},
                ))
    except Exception as exc:
        logger.debug("_check_overdue_agents failed for tenant %s: %s", tenant_id, exc)
    return signals


def _check_high_daily_cost(tenant_id: str) -> list[SignalEvent]:
    """Warn when a tenant is over 80 % of its daily budget."""
    signals: list[SignalEvent] = []
    try:
        from api.services.observability.cost_tracker import get_daily_cost
        from sqlmodel import Session, select
        from ktem.db.engine import engine
        from api.services.observability.cost_tracker import BudgetLimit

        with Session(engine) as session:
            budget = session.get(BudgetLimit, tenant_id)
        if not budget:
            return signals

        cost_info = get_daily_cost(tenant_id)
        spent = cost_info.get("total_cost_usd", 0.0)
        limit = budget.daily_limit_usd
        fraction = spent / limit if limit > 0 else 0.0
        if fraction >= 0.8:
            pct = round(fraction * 100, 1)
            severity = "critical" if fraction >= 1.0 else "warning"
            signals.append(SignalEvent(
                tenant_id=tenant_id,
                signal_type="high_daily_cost",
                severity=severity,
                title=f"Daily budget {pct}% used",
                summary=(
                    f"Tenant has spent ${spent:.4f} of its ${limit:.2f} daily limit "
                    f"({pct}%)."
                ),
                source_ref="cost_tracker",
                payload=cost_info,
            ))
    except Exception as exc:
        logger.debug("_check_high_daily_cost failed for tenant %s: %s", tenant_id, exc)
    return signals


# ── Detector ──────────────────────────────────────────────────────────────────

class SignalDetector:
    """Runs registered check functions and collects SignalEvent results."""

    def __init__(self) -> None:
        self._checks: dict[str, CheckFn] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register_check("overdue_agents", _check_overdue_agents)
        self.register_check("high_daily_cost", _check_high_daily_cost)

    def register_check(self, name: str, fn: CheckFn) -> None:
        self._checks[name] = fn

    def unregister_check(self, name: str) -> None:
        self._checks.pop(name, None)

    def run_checks(self, tenant_id: str) -> list[SignalEvent]:
        results: list[SignalEvent] = []
        for name, fn in list(self._checks.items()):
            try:
                events = fn(tenant_id)
                results.extend(events)
            except Exception as exc:
                logger.warning("Check '%s' raised for tenant %s: %s", name, tenant_id, exc)
        return results


_detector: SignalDetector | None = None


def get_signal_detector() -> SignalDetector:
    global _detector
    if _detector is None:
        _detector = SignalDetector()
    return _detector
