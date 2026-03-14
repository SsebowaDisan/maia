"""B2-05 — Multi-agent orchestrator (delegation layer).

Responsibility: extend the existing company_agent orchestrator to support
sub-agent delegation.  An orchestrator can call ``delegate_to_agent`` which
runs a child agent and returns its result.

Max delegation depth is enforced from the parent agent's config.
Each delegation emits activity events.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_DEFAULT_MAX_DEPTH = 3


class DelegationDepthError(Exception):
    pass


def delegate_to_agent(
    parent_agent_id: str,
    child_agent_id: str,
    task: str,
    context: dict[str, Any],
    *,
    tenant_id: str,
    run_id: str,
    current_depth: int = 0,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """Run a child agent as a sub-task and return its result.

    Args:
        parent_agent_id: ID of the delegating agent.
        child_agent_id: ID of the agent to delegate to.
        task: The natural-language task string for the child agent.
        context: Key-value context to inject into the child run.
        tenant_id: Active tenant.
        run_id: Parent run identifier (child gets a derived run_id).
        current_depth: How many delegation levels deep we already are.
        max_depth: Maximum depth before raising DelegationDepthError.
        on_event: Optional callback for activity events.

    Returns:
        dict with keys: ``success``, ``result``, ``child_run_id``, ``agent_id``.
    """
    if current_depth >= max_depth:
        raise DelegationDepthError(
            f"Delegation depth limit ({max_depth}) reached. "
            f"Parent: {parent_agent_id}, attempted child: {child_agent_id}."
        )

    child_run_id = f"{run_id}.{current_depth + 1}.{uuid.uuid4().hex[:8]}"

    _emit(on_event, {
        "event_type": "agent_delegated",
        "parent_agent_id": parent_agent_id,
        "child_agent_id": child_agent_id,
        "child_run_id": child_run_id,
        "task_preview": task[:200],
        "depth": current_depth + 1,
    })

    logger.info(
        "Delegating to agent '%s' (depth=%d, child_run_id=%s)",
        child_agent_id,
        current_depth + 1,
        child_run_id,
    )

    try:
        result = _run_child_agent(
            child_agent_id=child_agent_id,
            task=task,
            context=context,
            tenant_id=tenant_id,
            child_run_id=child_run_id,
            depth=current_depth + 1,
            max_depth=max_depth,
            on_event=on_event,
        )
        _emit(on_event, {
            "event_type": "agent_delegation_completed",
            "child_agent_id": child_agent_id,
            "child_run_id": child_run_id,
            "success": True,
        })
        return {"success": True, "result": result, "child_run_id": child_run_id, "agent_id": child_agent_id}

    except Exception as exc:
        logger.error("Child agent '%s' failed: %s", child_agent_id, exc, exc_info=True)
        _emit(on_event, {
            "event_type": "agent_delegation_failed",
            "child_agent_id": child_agent_id,
            "child_run_id": child_run_id,
            "error": str(exc)[:300],
        })
        return {
            "success": False,
            "result": None,
            "child_run_id": child_run_id,
            "agent_id": child_agent_id,
            "error": str(exc)[:300],
        }


def _run_child_agent(
    *,
    child_agent_id: str,
    task: str,
    context: dict[str, Any],
    tenant_id: str,
    child_run_id: str,
    depth: int,
    max_depth: int,
    on_event: Optional[Callable[[dict[str, Any]], None]],
) -> Any:
    """Actually run the child agent.  Delegates to the agent execution service."""
    from api.services.agents.definition_store import get_agent, load_schema

    record = get_agent(tenant_id, child_agent_id)
    if not record:
        raise ValueError(f"Child agent '{child_agent_id}' not found in tenant '{tenant_id}'.")

    schema = load_schema(record)

    # Build a minimal ChatRequest-like payload and run through the existing orchestrator
    # so we reuse all existing tool calling, memory, and streaming infrastructure.
    from api.services.agents.runner import run_agent_task

    result_parts: list[str] = []

    system_prompt = (schema.system_prompt or "") + (
        f"\n\nCONTEXT:\n{_format_context(context)}" if context else ""
    )

    # Collect streamed output into result
    for chunk in run_agent_task(
        task,
        tenant_id=tenant_id,
        run_id=child_run_id,
        system_prompt=system_prompt or None,
    ):
        text = chunk.get("text") or chunk.get("content") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            on_event({**chunk, "child_run_id": child_run_id, "depth": depth})

    return "".join(result_parts)


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass


def _format_context(context: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in context.items())
