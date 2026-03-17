"""Agent task runner — thin adapter around AgentOrchestrator.run_stream().

Responsibility: bridge Phase-2 agent execution to the existing
AgentOrchestrator API.  All Phase-2 code that needs to run an agent task
should call run_agent_task() from here.

The existing orchestrator exposes only:
    run_stream(*, user_id, conversation_id, request: ChatRequest, settings: dict)

This module builds the required ChatRequest and forwards the generator.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from typing import Any

logger = logging.getLogger(__name__)


def _prepare_memory_context(
    tenant_id: str,
    agent_id: str | None,
    task: str,
    k: int = 5,
) -> str:
    """Return a memory context block to prepend, or empty string on failure."""
    if not agent_id:
        return ""
    try:
        from api.services.agents.long_term_memory import recall_memories
        memories = recall_memories(tenant_id, agent_id, task, k=k)
        if not memories:
            return ""
        lines = ["[Relevant memories from previous runs:]"]
        for m in memories:
            lines.append(f"- {m['content']}")
        return "\n".join(lines)
    except Exception as exc:
        logger.debug("Memory recall failed for agent %s: %s", agent_id, exc)
        return ""


def run_agent_task(
    task: str,
    *,
    tenant_id: str,
    run_id: str | None = None,
    conversation_id: str | None = None,
    system_prompt: str | None = None,
    agent_mode: str = "company_agent",
    allowed_tool_ids: list[str] | None = None,
    agent_id: str | None = None,
    max_tool_calls: int | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Run an agent task through the existing AgentOrchestrator.

    Args:
        task: The natural-language task string.
        tenant_id: Tenant/user identifier (used as user_id for the orchestrator).
        run_id: Optional run identifier; used as conversation_id when no
            explicit conversation_id is given.
        conversation_id: Optional conversation identifier.
        system_prompt: Optional system prompt override.  Prepended to the
            task message because run_stream() has no system_override param.
        agent_mode: One of "ask", "company_agent", "deep_search".
        allowed_tool_ids: Optional allowlist from the agent definition's ``tools``
            field.  When provided the step planner restricts itself to only these
            tool IDs, enforcing the marketplace agent's declared capability scope.
        agent_id: When provided, top-k relevant long-term memories are recalled
            and prepended to the task context automatically (P7-04).
        max_tool_calls: CB06 — hard cap on tool invocations per run. When the
            limit is hit the run is stopped and a budget_exceeded event is emitted.

    Yields:
        Event dicts from the orchestrator — same format as the chat stream.
    """
    from api.services.agent.orchestration.app import get_orchestrator
    from api.schemas import ChatRequest

    effective_conversation_id = conversation_id or run_id or str(uuid.uuid4())

    # P7-04: prepend long-term memory context when an agent_id is known
    memory_context = _prepare_memory_context(tenant_id, agent_id, task)

    effective_message = task
    parts: list[str] = []
    if memory_context:
        parts.append(memory_context)
    if system_prompt:
        parts.append(system_prompt)
    if parts:
        effective_message = "\n\n".join(parts) + "\n\n" + task

    request = ChatRequest(
        message=effective_message,
        conversation_id=effective_conversation_id,
        agent_mode=agent_mode,  # type: ignore[arg-type]
    )

    settings: dict[str, Any] = {}
    if allowed_tool_ids:
        settings["__allowed_tool_ids"] = list(allowed_tool_ids)
    if max_tool_calls is not None:
        settings["__max_tool_calls"] = max_tool_calls

    # CB06: track tool call count and enforce the cap in the event stream
    tool_call_count = 0
    budget_exceeded = False

    orchestrator = get_orchestrator()
    try:
        for event in orchestrator.run_stream(
            user_id=tenant_id,
            conversation_id=effective_conversation_id,
            request=request,
            settings=settings,
        ):
            if budget_exceeded:
                break
            # Count tool-call events
            if max_tool_calls is not None and event.get("event_type") in (
                "tool_call", "tool_use", "tool_result"
            ):
                tool_call_count += 1
                if tool_call_count >= max_tool_calls:
                    budget_exceeded = True
                    logger.warning(
                        "run_agent_task: max_tool_calls=%d reached for agent=%s tenant=%s",
                        max_tool_calls, agent_id, tenant_id,
                    )
                    yield event
                    yield {
                        "event_type": "budget_exceeded",
                        "detail": f"Tool call limit of {max_tool_calls} reached. Run stopped.",
                        "tool_calls_made": tool_call_count,
                    }
                    break
            yield event
    except Exception as exc:
        logger.error("run_agent_task failed (tenant=%s): %s", tenant_id, exc, exc_info=True)
        yield {"event_type": "error", "detail": str(exc)[:300]}
