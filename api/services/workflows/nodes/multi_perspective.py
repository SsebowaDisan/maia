"""Multi-Perspective Debate node — runs 3-persona analysis on a topic.

step_config:
    persona_set: str  — "analysis" (default) or "research"
    topic_key: str    — input key for the topic (default "topic")
    context_key: str  — input key for supporting context (default "context")

Returns a dict with:
    synthesis: str        — merged analysis from all 3 perspectives
    perspectives: list    — individual perspective outputs
    persona_set: str      — which persona set was used
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)


@register("multi_perspective")
def handle_multi_perspective(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    cfg = step.step_config
    persona_set = str(cfg.get("persona_set", "analysis"))
    topic_key = str(cfg.get("topic_key", "topic"))
    context_key = str(cfg.get("context_key", "context"))

    topic = str(inputs.get(topic_key, "")).strip()
    context = str(inputs.get(context_key, "")).strip()

    if not topic:
        return {"synthesis": "", "perspectives": [], "error": "No topic provided"}

    if on_event:
        on_event({"event_type": "multi_perspective_started", "persona_set": persona_set})

    try:
        from api.services.agent.reasoning.multi_perspective import run_multi_perspective_debate_sync

        def _llm_call(system_prompt: str, user_prompt: str) -> str:
            from api.services.agents.runner import run_agent_task
            parts: list[str] = []
            for chunk in run_agent_task(
                user_prompt,
                system_prompt=system_prompt,
                max_tool_calls=0,
            ):
                text = chunk.get("text") or chunk.get("content") or ""
                if text:
                    parts.append(str(text))
            return "".join(parts)

        result = run_multi_perspective_debate_sync(
            topic=topic,
            context=context,
            llm_call_sync=_llm_call,
            persona_set=persona_set,
        )
    except Exception as exc:
        logger.warning("Multi-perspective debate failed: %s", exc, exc_info=True)
        return {"synthesis": "", "perspectives": [], "error": str(exc)[:300]}

    if on_event:
        on_event({"event_type": "multi_perspective_completed", "perspective_count": len(result.get("perspectives", []))})

    return result
