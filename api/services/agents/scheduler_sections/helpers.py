from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from ktem.db.engine import engine

if TYPE_CHECKING:
    from api.services.agents.scheduler import AgentSchedule

logger = logging.getLogger(__name__)


def fire_agent(tenant_id: str, agent_id: str) -> None:
    """Create and execute a scheduled agent run in the current thread."""
    logger.info("Firing scheduled run: agent=%s tenant=%s", agent_id, tenant_id)

    try:
        from api.services.observability.cost_tracker import assert_budget_ok

        assert_budget_ok(tenant_id)
    except Exception as budget_exc:
        logger.warning(
            "Scheduled run blocked for agent=%s tenant=%s: %s",
            agent_id,
            tenant_id,
            budget_exc,
        )
        return

    from api.services.agents.run_store import complete_run, create_run, fail_run

    run = create_run(tenant_id, agent_id, trigger_type="scheduled")
    run_start = time.time()
    task_completed = False
    tool_calls = 0
    try:
        from api.services.agents.definition_store import get_agent, load_schema
        from api.services.agents.runner import run_agent_task

        record = get_agent(tenant_id, agent_id)
        if not record:
            logger.warning(
                "Scheduled agent %s not found in tenant %s", agent_id, tenant_id
            )
            fail_run(run.id, error="Agent definition not found")
            return

        schema = load_schema(record)
        task = schema.description or f"Scheduled run for agent {schema.name}"
        allowed_tool_ids = list(schema.tools) if getattr(schema, "tools", None) else None

        from api.services.agent.live_events import get_live_event_broker

        broker = get_live_event_broker()
        run_id_str = str(run.id)
        result_parts: list[str] = []
        for chunk in run_agent_task(
            task,
            tenant_id=tenant_id,
            run_id=run.id,
            allowed_tool_ids=allowed_tool_ids,
        ):
            try:
                broker.publish(user_id=tenant_id, event=chunk, run_id=run_id_str)
            except Exception:
                pass
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                result_parts.append(str(text))
            if chunk.get("event_type") in (
                "tool_started",
                "tool_called",
                "step_complete",
            ):
                tool_calls += 1

        complete_run(run.id, result_summary=("".join(result_parts))[:500])
        task_completed = True
    except Exception as exc:
        fail_run(run.id, error=str(exc)[:300])
        raise
    finally:
        duration_ms = int((time.time() - run_start) * 1000)
        try:
            from api.services.marketplace.metering import record_usage

            record_usage(
                tenant_id,
                agent_id,
                run.id,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.debug(
                "record_usage failed for scheduled run %s", run.id, exc_info=True
            )
        try:
            from api.services.marketplace.benchmarks import submit_signal

            submit_signal(
                tenant_id,
                agent_id,
                task_completed=task_completed,
                quality_score=0.5,
                cost_usd=0.0,
            )
        except Exception:
            logger.debug(
                "submit_signal failed for scheduled run %s", run.id, exc_info=True
            )


def notify_schedule_paused(tenant_id: str, agent_id: str, failure_count: int) -> None:
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


def set_agent_run_cap(
    tenant_id: str, agent_id: str, max_runs_per_day: int | None
) -> bool:
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


def is_daily_budget_exceeded(schedule: AgentSchedule, now: float) -> bool:
    if schedule.max_runs_per_day is None:
        return False
    today = utc_date_str(now)
    if schedule.runs_today_date != today:
        return False
    return schedule.runs_today >= schedule.max_runs_per_day


def increment_daily_count(rec: AgentSchedule, now: float) -> None:
    today = utc_date_str(now)
    if rec.runs_today_date != today:
        rec.runs_today = 1
        rec.runs_today_date = today
    else:
        rec.runs_today = (rec.runs_today or 0) + 1


def utc_date_str(ts: float) -> str:
    import datetime as dt

    return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def get_schedule_health(tenant_id: str, agent_id: str) -> dict:
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


def seed_schedules_from_definitions() -> None:
    try:
        from api.services.agents.definition_store import list_agents, load_schema
        from api.services.agents.scheduler import register_schedule
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


def next_timestamp(cron_expression: str) -> float:
    try:
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            return time.time() + 3600

        import datetime as dt

        now = dt.datetime.utcnow()

        def matches(field: str, value: int) -> bool:
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
        candidate = now.replace(second=0, microsecond=0)
        for _ in range(10080):
            candidate += dt.timedelta(minutes=1)
            if (
                matches(month_f, candidate.month)
                and matches(dom_f, candidate.day)
                and matches(dow_f, candidate.weekday())
                and matches(hour_f, candidate.hour)
                and matches(minute_f, candidate.minute)
            ):
                return candidate.replace(tzinfo=dt.timezone.utc).timestamp()
        return time.time() + 3600
    except Exception:
        return time.time() + 3600
