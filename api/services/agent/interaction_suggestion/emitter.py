from __future__ import annotations

import logging
from typing import Any, Callable

from api.services.agent.models import AgentActivityEvent

from .config import (
    LLM_INTERACTION_SUGGESTIONS_ENABLED,
    LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE,
    LLM_INTERACTION_SUGGESTION_MAX_PER_STEP,
)
from .llm_adapter import generate_interaction_suggestion
from .schema import payload_to_metadata

logger = logging.getLogger(__name__)

# Tool prefixes whose surfaces are interactive enough to warrant suggestions.
# Analytics, API, and system tools are excluded — there is no visual surface.
_INTERACTIVE_PREFIXES: tuple[str, ...] = (
    "browser.",
    "web.",
    "marketing.web_research",
    "docs.",
    "workspace.docs",
    "sheets.",
    "workspace.sheets",
    "gmail.",
    "email.",
    "drive.",
)


def _is_interactive_tool(tool_id: str) -> bool:
    tid = str(tool_id or "").lower().strip()
    return any(
        tid.startswith(prefix) or tid == prefix.rstrip(".")
        for prefix in _INTERACTIVE_PREFIXES
    )


def maybe_emit_interaction_suggestion(
    *,
    tool_id: str,
    step_title: str,
    step_index: int,
    total_steps: int,
    step_why: str,
    step_params: dict[str, Any],
    task_context: str,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
    suggestions_emitted_this_step: list[Any],
) -> list[dict[str, Any]]:
    """Attempt to emit up to MAX_PER_STEP ``interaction_suggestion`` events before the step runs.

    Called pre-execution so hints reach the UI while the step is in progress,
    giving the user anticipatory visual cues rather than retrospective ones.

    Gating order
    ------------
    1. Feature flag ``MAIA_LLM_INTERACTION_SUGGESTIONS_ENABLED`` — must be True.
    2. Tool surface check — tool must belong to a browser/doc/email surface.
    3. Per-step cap — ``suggestions_emitted_this_step`` length vs MAX_PER_STEP.
    4. LLM call + validation — invalid or low-confidence responses are dropped.
    5. Confidence threshold — each suggestion's confidence must reach MIN_CONFIDENCE.

    Safety guarantees
    -----------------
    * All emitted event types are ``interaction_suggestion`` — never executable types.
    * ``metadata[\"advisory\"] = True`` and ``metadata[\"__no_execution\"] = True`` are
      always set by ``payload_to_metadata`` and cannot be overridden by the LLM.
    * This function never modifies ``ExecutionState``, queues real tool calls, or
      writes to any external system.

    Observability
    -------------
    Every invocation logs an ``interaction_suggestion.outcome`` record with:
    ``tool_id``, ``step``, ``enabled``, ``interactive``, ``emitted_count``, ``total_generated``.
    """
    enabled = LLM_INTERACTION_SUGGESTIONS_ENABLED
    interactive = _is_interactive_tool(tool_id)
    under_cap = len(suggestions_emitted_this_step) < LLM_INTERACTION_SUGGESTION_MAX_PER_STEP

    if not enabled or not interactive or not under_cap:
        logger.debug(
            "interaction_suggestion.gated: tool_id=%s enabled=%s interactive=%s under_cap=%s",
            tool_id,
            enabled,
            interactive,
            under_cap,
        )
        return []

    suggestions = generate_interaction_suggestion(
        tool_id=tool_id,
        step_title=step_title,
        step_why=step_why,
        step_params=step_params,
        task_context=task_context,
        step_index=step_index,
        total_steps=total_steps,
    )

    scene_surface = _resolve_scene_surface(tool_id)
    emitted: list[dict[str, Any]] = []

    for suggestion_index, suggestion in enumerate(suggestions):
        if len(suggestions_emitted_this_step) >= LLM_INTERACTION_SUGGESTION_MAX_PER_STEP:
            break

        if suggestion.confidence < LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE:
            logger.debug(
                "interaction_suggestion.below_threshold: tool_id=%s index=%d confidence=%.3f",
                tool_id,
                suggestion_index,
                suggestion.confidence,
            )
            continue

        # Build event metadata — advisory guards are injected by payload_to_metadata.
        metadata = payload_to_metadata(suggestion)
        metadata["tool_id"] = tool_id
        metadata["step"] = step_index
        metadata["suggestion_index"] = suggestion_index
        metadata["llm_interaction_suggestion"] = True
        metadata["scene_surface"] = scene_surface
        metadata["event_family"] = "interaction"

        title_body = f"{suggestion.action} {suggestion.target_label}".strip()
        event = activity_event_factory(
            event_type="interaction_suggestion",
            title=f"Interaction hint: {title_body}"[:80],
            detail=suggestion.reason,
            metadata=metadata,
        )

        suggestions_emitted_this_step.append(step_index)
        emitted.append(emit_event(event))

    logger.info(
        "interaction_suggestion.outcome",
        extra={
            "tool_id": tool_id,
            "step": step_index,
            "enabled": enabled,
            "interactive": interactive,
            "total_generated": len(suggestions),
            "emitted_count": len(emitted),
        },
    )

    return emitted


def _resolve_scene_surface(tool_id: str) -> str:
    tid = str(tool_id or "").lower().strip()
    if tid.startswith("browser.") or tid.startswith("web.") or tid == "marketing.web_research":
        return "browser"
    if tid.startswith("gmail.") or tid.startswith("email."):
        return "email"
    if (
        tid.startswith("docs.")
        or tid.startswith("workspace.docs")
        or tid.startswith("sheets.")
        or tid.startswith("workspace.sheets")
        or tid.startswith("drive.")
    ):
        return "document"
    return "document"
