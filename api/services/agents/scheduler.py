"""B2-07 - Scheduled trigger engine.

Responsibility: run agents on cron schedules by extending the existing
thread-based report_scheduler infrastructure.

Reads all active agents with ``trigger.family == "scheduled"`` at startup
and whenever schedules are registered. Uses a background thread + poll loop
(APScheduler is not installed - extends existing pattern from report_scheduler).

Schedule storage: DB-backed via a small SQLModel table.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine
from api.services.agents.scheduler_sections.helpers import (
    fire_agent as _fire_agent,
    get_agent_usage,
    get_schedule_health,
    increment_daily_count as _increment_daily_count,
    is_daily_budget_exceeded as _is_daily_budget_exceeded,
    next_timestamp as _next_timestamp,
    notify_schedule_paused as _notify_schedule_paused,
    seed_schedules_from_definitions as _seed_schedules_from_definitions,
    set_agent_run_cap,
)

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60


class AgentSchedule(SQLModel, table=True):
    __tablename__ = "maia_agent_schedule"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    cron_expression: str
    enabled: bool = True
    last_run_at: Optional[float] = Field(default=None)
    next_run_at: float = 0.0
    failure_count: int = 0
    last_failure_at: Optional[float] = Field(default=None)
    retry_after: Optional[float] = Field(default=None)
    max_runs_per_day: Optional[int] = Field(default=None)
    runs_today: int = 0
    runs_today_date: str = ""



def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_schedule_columns()



def _migrate_schedule_columns() -> None:
    """Add columns introduced after initial maia_agent_schedule table creation."""
    try:
        from sqlalchemy import inspect as _inspect, text

        insp = _inspect(engine)
        existing = {col["name"] for col in insp.get_columns("maia_agent_schedule")}
    except Exception:
        return

    additions = [
        ("failure_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_failure_at", "FLOAT"),
        ("retry_after", "FLOAT"),
        ("max_runs_per_day", "INTEGER"),
        ("runs_today", "INTEGER NOT NULL DEFAULT 0"),
        ("runs_today_date", "VARCHAR NOT NULL DEFAULT ''"),
    ]
    with Session(engine) as session:
        for col, defn in additions:
            if col not in existing:
                session.exec(text(f"ALTER TABLE maia_agent_schedule ADD COLUMN {col} {defn}"))
                logger.info("agent_schedule schema: added column %r", col)
        session.commit()



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
            .where(AgentSchedule.enabled == True)
        ).all()


class AgentScheduler:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        _ensure_tables()
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
                .where(AgentSchedule.enabled == True)
                .where(AgentSchedule.next_run_at <= now)
            ).all()

        for schedule in due:
            if schedule.retry_after and schedule.retry_after > now:
                continue
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
                enqueued = False
                try:
                    from api.services.tasks.queue import get_task_queue

                    queue = get_task_queue()
                    queue.enqueue(
                        "agent.scheduled_run",
                        {"tenant_id": schedule.tenant_id, "agent_id": schedule.agent_id},
                        priority=5,
                    )
                    enqueued = True
                except Exception:
                    pass
                if not enqueued:
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
                    rec.failure_count = 0
                    rec.last_failure_at = None
                    rec.retry_after = None
                    rec.next_run_at = _next_timestamp(rec.cron_expression)
                    _increment_daily_count(rec, now)
                else:
                    rec.failure_count = (rec.failure_count or 0) + 1
                    rec.last_failure_at = now
                    backoff_minutes = [5, 15, 45]
                    attempt = rec.failure_count - 1
                    if attempt < len(backoff_minutes):
                        rec.retry_after = now + backoff_minutes[attempt] * 60
                    else:
                        rec.retry_after = None
                        rec.next_run_at = _next_timestamp(rec.cron_expression)
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


_scheduler: Optional[AgentScheduler] = None
_lock = threading.Lock()



def get_agent_scheduler() -> AgentScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = AgentScheduler()
    return _scheduler
