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


def run_agent_task(
    task: str,
    *,
    tenant_id: str,
    run_id: str | None = None,
    conversation_id: str | None = None,
    system_prompt: str | None = None,
    agent_mode: str = "company_agent",
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

    Yields:
        Event dicts from the orchestrator — same format as the chat stream.
    """
    from api.services.agent.orchestration.app import get_orchestrator
    from api.schemas import ChatRequest

    effective_conversation_id = conversation_id or run_id or str(uuid.uuid4())

    effective_message = task
    if system_prompt:
        effective_message = f"{system_prompt}\n\n{task}"

    request = ChatRequest(
        message=effective_message,
        conversation_id=effective_conversation_id,
        agent_mode=agent_mode,  # type: ignore[arg-type]
    )

    orchestrator = get_orchestrator()
    try:
        yield from orchestrator.run_stream(
            user_id=tenant_id,
            conversation_id=effective_conversation_id,
            request=request,
            settings={},
        )
    except Exception as exc:
        logger.error("run_agent_task failed (tenant=%s): %s", tenant_id, exc, exc_info=True)
        yield {"event_type": "error", "detail": str(exc)[:300]}
