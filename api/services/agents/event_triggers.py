"""B2-08 — Event trigger engine.

Responsibility: receive webhook events from external connectors and fan out
to agents whose ``trigger.family == "on_event"`` matches the event pattern.

Agents are queued for async execution in a background thread pool.
"""
from __future__ import annotations

import fnmatch
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="EventTrigger")


# ── Subscription table ─────────────────────────────────────────────────────────

class EventSubscription(SQLModel, table=True):
    __tablename__ = "maia_event_subscription"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    event_pattern: str  # glob pattern, e.g. "salesforce.deal.*"
    connector_id: str
    enabled: bool = True


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Public API ─────────────────────────────────────────────────────────────────

def subscribe_agent_to_event(
    tenant_id: str,
    agent_id: str,
    event_pattern: str,
    connector_id: str,
) -> EventSubscription:
    """Register an agent to receive events matching a glob pattern."""
    _ensure_tables()
    with Session(engine) as session:
        existing = session.exec(
            select(EventSubscription)
            .where(EventSubscription.tenant_id == tenant_id)
            .where(EventSubscription.agent_id == agent_id)
            .where(EventSubscription.event_pattern == event_pattern)
        ).first()
        if existing:
            existing.enabled = True
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        sub = EventSubscription(
            tenant_id=tenant_id,
            agent_id=agent_id,
            event_pattern=event_pattern,
            connector_id=connector_id,
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        return sub


def unsubscribe_agent(tenant_id: str, agent_id: str, event_pattern: str) -> bool:
    with Session(engine) as session:
        sub = session.exec(
            select(EventSubscription)
            .where(EventSubscription.tenant_id == tenant_id)
            .where(EventSubscription.agent_id == agent_id)
            .where(EventSubscription.event_pattern == event_pattern)
        ).first()
        if not sub:
            return False
        sub.enabled = False
        session.add(sub)
        session.commit()
    return True


def list_subscriptions(tenant_id: str) -> Sequence[EventSubscription]:
    with Session(engine) as session:
        return session.exec(
            select(EventSubscription)
            .where(EventSubscription.tenant_id == tenant_id)
            .where(EventSubscription.enabled == True)  # noqa: E712
        ).all()


def handle_webhook_event(
    tenant_id: str,
    connector_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> list[str]:
    """Receive a webhook event and fire all matching agent subscriptions.

    Returns list of run_ids that were queued.
    """
    _ensure_tables()
    full_event = f"{connector_id}.{event_type}"
    logger.info("Webhook event: %s for tenant %s", full_event, tenant_id)

    # Find all agents subscribed to a matching pattern
    with Session(engine) as session:
        subs = session.exec(
            select(EventSubscription)
            .where(EventSubscription.tenant_id == tenant_id)
            .where(EventSubscription.enabled == True)  # noqa: E712
        ).all()

    matched: list[EventSubscription] = [
        s for s in subs if fnmatch.fnmatch(full_event, s.event_pattern)
    ]

    run_ids: list[str] = []
    for sub in matched:
        run_ids.append(_queue_agent_run(tenant_id, sub.agent_id, full_event, payload))

    logger.info(
        "Event %s matched %d agent(s) in tenant %s",
        full_event,
        len(matched),
        tenant_id,
    )
    return run_ids


# ── Seed from definitions ─────────────────────────────────────────────────────

def seed_subscriptions_from_definitions() -> None:
    """Auto-subscribe agents whose trigger family is on_event."""
    try:
        from api.services.agents.definition_store import list_agents, load_schema
        from api.services.tenants.store import list_tenants

        for tenant in list_tenants():
            for record in list_agents(tenant.id):
                try:
                    schema = load_schema(record)
                    trigger = getattr(schema, "trigger", None)
                    if not trigger:
                        continue
                    if getattr(trigger, "family", None) != "on_event":
                        continue
                    event_type = getattr(trigger, "event_type", None)
                    connector_id = getattr(trigger, "source_connector_id", "unknown")
                    if event_type:
                        subscribe_agent_to_event(
                            tenant.id,
                            record.agent_id,
                            event_type,
                            connector_id,
                        )
                except Exception:
                    pass
    except Exception:
        logger.debug("Subscription seeding failed", exc_info=True)


# ── Background execution ───────────────────────────────────────────────────────

def _queue_agent_run(
    tenant_id: str,
    agent_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    # Guard: check budget before queuing.  Blocked runs are logged and not queued.
    try:
        from api.services.observability.cost_tracker import assert_budget_ok
        assert_budget_ok(tenant_id)
    except Exception as budget_exc:
        logger.warning(
            "Event-triggered run blocked for agent=%s tenant=%s: %s",
            agent_id, tenant_id, budget_exc,
        )
        # Return a synthetic id so the caller doesn't crash; run is not persisted.
        import uuid
        return f"blocked-{uuid.uuid4()}"

    from api.services.agents.run_store import create_run

    run = create_run(tenant_id, agent_id, trigger_type="event")
    # Try to enqueue via task queue; fall back to direct thread pool execution
    _enqueued = False
    try:
        from api.services.tasks.queue import get_task_queue
        queue = get_task_queue()
        queue.enqueue(
            "agent.event_run",
            {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "event_type": event_type,
                "event_payload": payload,
            },
            priority=5,
        )
        _enqueued = True
    except Exception:
        pass
    if not _enqueued:
        _executor.submit(_run_agent_for_event, tenant_id, agent_id, run.id, event_type, payload)
    return run.id


def _run_agent_for_event(
    tenant_id: str,
    agent_id: str,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    import time as _time
    from api.services.agents.run_store import complete_run, fail_run

    _run_start = _time.time()
    task_completed = False
    tool_calls = 0
    try:
        from api.services.agents.definition_store import get_agent, load_schema
        from api.services.agents.runner import run_agent_task

        record = get_agent(tenant_id, agent_id)
        if not record:
            fail_run(run_id, error="Agent not found")
            return

        schema = load_schema(record)
        allowed_tool_ids = list(schema.tools) if getattr(schema, "tools", None) else None
        task = (
            f"Event received: {event_type}\n"
            f"Payload: {str(payload)[:500]}\n\n"
            f"Task: {schema.description or 'Process this event.'}"
        )

        result_parts: list[str] = []
        for chunk in run_agent_task(task, tenant_id=tenant_id, run_id=run_id, allowed_tool_ids=allowed_tool_ids):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                result_parts.append(str(text))
            if chunk.get("event_type") in ("tool_started", "tool_called", "step_complete"):
                tool_calls += 1

        complete_run(run_id, result_summary=("".join(result_parts))[:500])
        task_completed = True
    except Exception as exc:
        fail_run(run_id, error=str(exc)[:300])
        logger.error("Event-triggered agent %s failed: %s", agent_id, exc, exc_info=True)
    finally:
        duration_ms = int((_time.time() - _run_start) * 1000)
        try:
            from api.services.marketplace.metering import record_usage
            record_usage(
                tenant_id, agent_id, run_id,
                tool_calls=tool_calls,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.debug("record_usage failed for event run %s", run_id, exc_info=True)
        try:
            from api.services.marketplace.benchmarks import submit_signal
            submit_signal(
                tenant_id, agent_id,
                task_completed=task_completed,
                quality_score=0.5,
                cost_usd=0.0,
            )
        except Exception:
            logger.debug("submit_signal failed for event run %s", run_id, exc_info=True)
