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
    last_run_at: Optional[float] = None
    # Pre-computed: next UTC unix timestamp to fire (set on register or after run)
    next_run_at: float = 0.0


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


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
            try:
                _fire_agent(schedule.tenant_id, schedule.agent_id)
            except Exception:
                logger.error(
                    "Scheduled run failed for agent %s/%s",
                    schedule.tenant_id,
                    schedule.agent_id,
                    exc_info=True,
                )
            with Session(engine) as session:
                rec = session.get(AgentSchedule, schedule.id)
                if rec:
                    rec.last_run_at = now
                    rec.next_run_at = _next_timestamp(rec.cron_expression)
                    session.add(rec)
                    session.commit()


def _fire_agent(tenant_id: str, agent_id: str) -> None:
    """Create and execute a scheduled agent run in the current thread."""
    logger.info("Firing scheduled run: agent=%s tenant=%s", agent_id, tenant_id)
    from api.services.agents.run_store import create_run, complete_run, fail_run

    run = create_run(tenant_id, agent_id, trigger_type="scheduled")
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

        result_parts: list[str] = []
        for chunk in run_agent_task(task, tenant_id=tenant_id, run_id=run.id):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                result_parts.append(str(text))

        complete_run(run.id, result_summary=("".join(result_parts))[:500])
    except Exception as exc:
        fail_run(run.id, error=str(exc)[:300])
        raise


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

        # Scan up to 400 minutes forward
        candidate = now.replace(second=0, microsecond=0)
        for _ in range(400):
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
