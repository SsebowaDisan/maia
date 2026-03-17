"""B2-07 — Scheduled trigger engine.

Responsibility: run agents on cron schedules by extending the existing
thread-based report_scheduler infrastructure.

Reads all active agents with ``trigger.family == "scheduled"`` at startup
and whenever schedules are registered.  Uses a background thread + poll loop
(APScheduler is not installed — extends existing pattern from report_scheduler).

Schedule storage: DB-backed via a small SQLModel table.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60  # check every minute


class AgentSchedule(SQLModel, table=True):
    __tablename__ = "maia_agent_schedule"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    cron_expression: str
    enabled: bool = True
    last_run_at: Optional[float] = Field(default=None)
    # Pre-computed: next UTC unix timestamp to fire (set on register or after run)
    next_run_at: float = 0.0

    # ── B10: Failure recovery fields ──────────────────────────────────────────
    failure_count: int = 0          # consecutive full-cron-tick failures
    last_failure_at: Optional[float] = Field(default=None)
    # Retry-after timestamp: set during exponential back-off retries
    retry_after: Optional[float] = Field(default=None)

    # ── B12: Per-agent budget controls ────────────────────────────────────────
    max_runs_per_day: Optional[int] = Field(default=None)   # None = unlimited
    runs_today: int = 0             # count of runs in the current UTC day
    runs_today_date: str = ""       # ISO date string "YYYY-MM-DD" for day tracking


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_schedule_columns()


def _migrate_schedule_columns() -> None:
    """Add columns introduced after initial maia_agent_schedule table creation.

    Covers B10 (failure recovery) and B12 (per-agent budget) fields.
    Safe to call on every startup — idempotent.
    """
    try:
        from sqlalchemy import inspect as _inspect, text
        insp = _inspect(engine)
        existing = {col["name"] for col in insp.get_columns("maia_agent_schedule")}
    except Exception:
        return  # Table not yet created; create_all above will handle it

    additions = [
        # B10 — failure recovery
        ("failure_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_failure_at", "FLOAT"),
        ("retry_after", "FLOAT"),
        # B12 — per-agent daily budget
        ("max_runs_per_day", "INTEGER"),
        ("runs_today", "INTEGER NOT NULL DEFAULT 0"),
        ("runs_today_date", "VARCHAR NOT NULL DEFAULT ''"),
    ]
    with Session(engine) as session:
        for col, defn in additions:
            if col not in existing:
                session.exec(text(f"ALTER TABLE maia_agent_schedule ADD COLUMN {col} {defn}"))  # type: ignore[call-overload]
                logger.info("agent_schedule schema: added column %r", col)
        session.commit()


# ── Public API ─────────────────────────────────────────────────────────────────

def register_schedule(tenant_id: str, agent_id: str, cron_expression: str) -> AgentSchedule:
    """Register or update the schedule for an agent."""
    _ensure_tables()
    with Session(engine) as session:
        existing = session.exec(
            select(AgentSchedule)
            .where(AgentSchedule.tenant_id == tenant_id)
            .where(AgentSchedule.agent_id == agent_id)
        ).first()
        if existing:
            existing.cron_expression = cron_expression
            existing.enabled = True
            existing.next_run_at = _next_timestamp(cron_expression)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        schedule = AgentSchedule(
            tenant_id=tenant_id,
            agent_id=agent_id,
            cron_expression=cron_expression,
            next_run_at=_next_timestamp(cron_expression),
        )
        session.add(schedule)
        session.commit()
        session.refresh(schedule)
        return schedule


def unregister_schedule(tenant_id: str, agent_id: str) -> bool:
    with Session(engine) as session:
        schedule = session.exec(
            select(AgentSchedule)
            .where(AgentSchedule.tenant_id == tenant_id)
            .where(AgentSchedule.agent_id == agent_id)
        ).first()
        if not schedule:
            return False
        schedule.enabled = False
        session.add(schedule)
        session.commit()
    return True


def list_schedules(tenant_id: str) -> Sequence[AgentSchedule]:
    with Session(engine) as session:
        return session.exec(
            select(AgentSchedule)
            .where(AgentSchedule.tenant_id == tenant_id)
            .where(AgentSchedule.enabled == True)  # noqa: E712
        ).all()


# ── Scheduler thread ───────────────────────────────────────────────────────────

class AgentScheduler:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        _ensure_tables()
        # Seed schedules from agent definitions
        _seed_schedules_from_definitions()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AgentScheduler")
        self._thread.start()
        logger.info("AgentScheduler started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("AgentScheduler stopped")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                logger.error("AgentScheduler tick error", exc_info=True)
            self._stop_event.wait(timeout=_CHECK_INTERVAL_SECONDS)

    def _tick(self) -> None:
        now = time.time()
        with Session(engine) as session:
            due = session.exec(
                select(AgentSchedule)
                .where(AgentSchedule.enabled == True)  # noqa: E712
                .where(AgentSchedule.next_run_at <= now)
            ).all()

        for schedule in due:
            # B10: Skip if we are in an exponential back-off window
            if schedule.retry_after and schedule.retry_after > now:
                continue

            # B12: Enforce per-agent daily run cap
            if _is_daily_budget_exceeded(schedule, now):
                logger.debug(
                    "Daily run cap reached for agent %s/%s (max=%s)",
                    schedule.tenant_id,
                    schedule.agent_id,
                    schedule.max_runs_per_day,
                )
                continue

            success = False
            try:
                _fire_agent(schedule.tenant_id, schedule.agent_id)
                success = True
            except Exception:
                logger.error(
                    "Scheduled run failed for agent %s/%s",
                    schedule.tenant_id,
                    schedule.agent_id,
                    exc_info=True,
                )

            with Session(engine) as session:
                rec = session.get(AgentSchedule, schedule.id)
                if not rec:
                    continue
                rec.last_run_at = now
                if success:
                    # Reset failure tracking on success
                    rec.failure_count = 0
                    rec.last_failure_at = None
                    rec.retry_after = None
                    rec.next_run_at = _next_timestamp(rec.cron_expression)
                    # B12: Increment daily run count
                    _increment_daily_count(rec, now)
                else:
                    rec.failure_count = (rec.failure_count or 0) + 1
                    rec.last_failure_at = now
                    # B10: Exponential back-off retry within same cron window
                    # Retries: 5 min → 15 min → 45 min (3 attempts), then full tick
                    backoff_minutes = [5, 15, 45]
                    attempt = rec.failure_count - 1
                    if attempt < len(backoff_minutes):
                        rec.retry_after = now + backoff_minutes[attempt] * 60
                        # Keep next_run_at so we don't skip the window entirely
                    else:
                        rec.retry_after = None
                        rec.next_run_at = _next_timestamp(rec.cron_expression)

                    # B10: Auto-pause after 7 consecutive tick failures
                    if rec.failure_count >= 7:
                        rec.enabled = False
                        logger.warning(
                            "Auto-pausing schedule for agent %s/%s after %d consecutive failures",
                            rec.tenant_id,
                            rec.agent_id,
                            rec.failure_count,
                        )
                        _notify_schedule_paused(rec.tenant_id, rec.agent_id, rec.failure_count)

                session.add(rec)
                session.commit()


def _fire_agent(tenant_id: str, agent_id: str) -> None:
    """Create and execute a scheduled agent run in the current thread."""
    logger.info("Firing scheduled run: agent=%s tenant=%s", agent_id, tenant_id)

    # Guard: check daily budget before starting the run.
    try:
        from api.services.observability.cost_tracker import assert_budget_ok, BudgetExceededError
        assert_budget_ok(tenant_id)
    except Exception as budget_exc:
        logger.warning(
            "Scheduled run blocked for agent=%s tenant=%s: %s",
            agent_id, tenant_id, budget_exc,
        )
        return

    from api.services.agents.run_store import create_run, complete_run, fail_run

    run = create_run(tenant_id, agent_id, trigger_type="scheduled")
    _run_start = time.time()
    task_completed = False
    tool_calls = 0
    try:
        from api.services.agents.definition_store import get_agent, load_schema
        from api.services.agents.runner import run_agent_task

        record = get_agent(tenant_id, agent_id)
        if not record:
            logger.warning("Scheduled agent %s not found in tenant %s", agent_id, tenant_id)
            fail_run(run.id, error="Agent definition not found")
            return

        schema = load_schema(record)
        task = schema.description or f"Scheduled run for agent {schema.name}"
        allowed_tool_ids = list(schema.tools) if getattr(schema, "tools", None) else None

        from api.services.agent.live_events import get_live_event_broker
        _broker = get_live_event_broker()
        _run_id_str = str(run.id)
        result_parts: list[str] = []
        for chunk in run_agent_task(task, tenant_id=tenant_id, run_id=run.id, allowed_tool_ids=allowed_tool_ids):
            try:
                _broker.publish(user_id=tenant_id, event=chunk, run_id=_run_id_str)
            except Exception:
                pass
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                result_parts.append(str(text))
            if chunk.get("event_type") in ("tool_started", "tool_called", "step_complete"):
                tool_calls += 1

        complete_run(run.id, result_summary=("".join(result_parts))[:500])
        task_completed = True
    except Exception as exc:
        fail_run(run.id, error=str(exc)[:300])
        raise
    finally:
        duration_ms = int((time.time() - _run_start) * 1000)
        try:
            from api.services.marketplace.metering import record_usage
            record_usage(
                tenant_id, agent_id, run.id,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.debug("record_usage failed for scheduled run %s", run.id, exc_info=True)
        try:
            from api.services.marketplace.benchmarks import submit_signal
            submit_signal(
                tenant_id, agent_id,
                task_completed=task_completed,
                quality_score=0.5,
                cost_usd=0.0,
            )
        except Exception:
            logger.debug("submit_signal failed for scheduled run %s", run.id, exc_info=True)


def _notify_schedule_paused(tenant_id: str, agent_id: str, failure_count: int) -> None:
    """Best-effort notification to the agent owner when a schedule is auto-paused."""
    try:
        from api.services.agents.definition_store import get_agent
        record = get_agent(tenant_id, agent_id)
        if record:
            logger.info(
                "Schedule auto-paused notification: tenant=%s agent=%s failures=%d owner=%s",
                tenant_id,
                agent_id,
                failure_count,
                record.created_by_user_id,
            )
    except Exception:
        logger.debug("Failed to dispatch pause notification", exc_info=True)


def set_agent_run_cap(tenant_id: str, agent_id: str, max_runs_per_day: int | None) -> bool:
    """B12: Set or clear the daily run cap for a scheduled agent."""
    with Session(engine) as session:
        rec = session.exec(
            select(AgentSchedule)
            .where(AgentSchedule.tenant_id == tenant_id)
            .where(AgentSchedule.agent_id == agent_id)
        ).first()
        if not rec:
            return False
        rec.max_runs_per_day = max_runs_per_day
        session.add(rec)
        session.commit()
    return True


def get_agent_usage(tenant_id: str, agent_id: str) -> dict:
    """B12: Return run count and daily cap for a scheduled agent."""
    with Session(engine) as session:
        rec = session.exec(
            select(AgentSchedule)
            .where(AgentSchedule.tenant_id == tenant_id)
            .where(AgentSchedule.agent_id == agent_id)
        ).first()
    if not rec:
        return {"found": False}
    return {
        "found": True,
        "runs_today": rec.runs_today,
        "runs_today_date": rec.runs_today_date,
        "max_runs_per_day": rec.max_runs_per_day,
        "cap_active": rec.max_runs_per_day is not None,
    }


def _is_daily_budget_exceeded(schedule: AgentSchedule, now: float) -> bool:
    """B12: Return True if the per-agent daily run cap has been reached."""
    if schedule.max_runs_per_day is None:
        return False
    today = _utc_date_str(now)
    if schedule.runs_today_date != today:
        return False  # New day — counter will be reset on next increment
    return schedule.runs_today >= schedule.max_runs_per_day


def _increment_daily_count(rec: AgentSchedule, now: float) -> None:
    """B12: Increment (or reset) the daily run counter."""
    today = _utc_date_str(now)
    if rec.runs_today_date != today:
        rec.runs_today = 1
        rec.runs_today_date = today
    else:
        rec.runs_today = (rec.runs_today or 0) + 1


def _utc_date_str(ts: float) -> str:
    import datetime as _dt
    return _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def get_schedule_health(tenant_id: str, agent_id: str) -> dict:
    """B10: Return failure count, last success, last failure for a schedule."""
    with Session(engine) as session:
        rec = session.exec(
            select(AgentSchedule)
            .where(AgentSchedule.tenant_id == tenant_id)
            .where(AgentSchedule.agent_id == agent_id)
        ).first()
    if not rec:
        return {"found": False}
    return {
        "found": True,
        "enabled": rec.enabled,
        "failure_count": rec.failure_count,
        "last_run_at": rec.last_run_at,
        "last_failure_at": rec.last_failure_at,
        "next_run_at": rec.next_run_at,
        "retry_after": rec.retry_after,
    }


def _seed_schedules_from_definitions() -> None:
    """Auto-register schedules for all agents with scheduled triggers."""
    try:
        from api.services.agents.definition_store import list_agents, load_schema
        from api.services.tenants.store import list_tenants

        for tenant in list_tenants():
            for record in list_agents(tenant.id):
                try:
                    schema = load_schema(record)
                    trigger = getattr(schema, "trigger", None)
                    if trigger and getattr(trigger, "family", None) == "scheduled":
                        cron = getattr(trigger, "cron_expression", None)
                        if cron:
                            register_schedule(tenant.id, record.agent_id, cron)
                except Exception:
                    pass
    except Exception:
        logger.debug("Schedule seeding failed", exc_info=True)


def _next_timestamp(cron_expression: str) -> float:
    """Parse a 5-field cron expression and return the next fire time as Unix timestamp.

    Simplified implementation for `minute hour dom month dow` format.
    Falls back to 1-hour delay for expressions that cannot be parsed.
    """
    try:
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            return time.time() + 3600

        import datetime as dt

        now = dt.datetime.utcnow()

        def _matches(field: str, value: int) -> bool:
            if field == "*":
                return True
            if "/" in field:
                base, step = field.split("/", 1)
                start = 0 if base == "*" else int(base)
                return (value - start) % int(step) == 0
            if "-" in field:
                lo, hi = field.split("-")
                return int(lo) <= value <= int(hi)
            if "," in field:
                return value in {int(v) for v in field.split(",")}
            return value == int(field)

        minute_f, hour_f, dom_f, month_f, dow_f = parts

        # Scan up to 10,080 minutes forward (one week) to cover weekly/monthly schedules
        candidate = now.replace(second=0, microsecond=0)
        for _ in range(10080):
            candidate += dt.timedelta(minutes=1)
            if (
                _matches(month_f, candidate.month)
                and _matches(dom_f, candidate.day)
                and _matches(dow_f, candidate.weekday())
                and _matches(hour_f, candidate.hour)
                and _matches(minute_f, candidate.minute)
            ):
                return candidate.replace(tzinfo=dt.timezone.utc).timestamp()

        return time.time() + 3600
    except Exception:
        return time.time() + 3600


# ── Singleton ──────────────────────────────────────────────────────────────────

_scheduler: Optional[AgentScheduler] = None
_lock = threading.Lock()


def get_agent_scheduler() -> AgentScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = AgentScheduler()
    return _scheduler
