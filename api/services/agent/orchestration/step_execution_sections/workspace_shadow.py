from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.models import AgentActivityEvent, utc_now
from api.services.agent.planner import PlannedStep
from api.services.agent.policy import ACCESS_MODE_FULL

from ..models import ExecutionState
from ..text_helpers import extract_action_artifact_metadata


def run_workspace_shadow_logging(
    *,
    access_context: Any,
    execution_prompt: str,
    state: ExecutionState,
    step: PlannedStep,
    index: int,
    result: Any,
    registry: Any,
    run_tool_live: Callable[..., Generator[dict[str, Any], None, Any]],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    if not state.deep_workspace_logging_enabled or step.tool_id in (
        "workspace.docs.research_notes",
        "workspace.sheets.track_step",
    ):
        return

    log_steps = [
        PlannedStep(
            tool_id="workspace.sheets.track_step",
            title=f"Track completion: {step.title}",
            params={
                "step_name": step.title,
                "status": "completed",
                "detail": result.summary,
                "source_url": (result.sources[0].url if result.sources else ""),
            },
        ),
    ]
    for shadow_step in log_steps:
        shadow_started_at = utc_now().isoformat()
        shadow_params = dict(shadow_step.params)
        if (
            access_context.access_mode == ACCESS_MODE_FULL
            and access_context.full_access_enabled
        ):
            shadow_params.setdefault("confirmed", True)
        try:
            shadow_result = yield from run_tool_live(
                step=shadow_step,
                step_index=index,
                prompt=execution_prompt,
                params=shadow_params,
            )
            shadow_metadata = extract_action_artifact_metadata(
                shadow_result.data,
                step=index,
            )
            shadow_metadata["shadow"] = True
            shadow_action = registry.get(shadow_step.tool_id).to_action(
                status="success",
                summary=shadow_result.summary,
                started_at=shadow_started_at,
                metadata=shadow_metadata,
            )
            state.all_actions.append(shadow_action)
            state.all_sources.extend(shadow_result.sources)
            shadow_completed = activity_event_factory(
                event_type="tool_completed",
                title=f"Completed: {shadow_step.title}",
                detail=shadow_result.summary,
                metadata={
                    "tool_id": shadow_step.tool_id,
                    "step": index,
                    "shadow": True,
                },
            )
            yield emit_event(shadow_completed)
        except Exception as shadow_exc:
            if any(
                marker in str(shadow_exc).lower()
                for marker in ("google_tokens_missing", "oauth", "refresh_token")
            ):
                state.deep_workspace_logging_enabled = False
                if not state.deep_workspace_warning_emitted:
                    state.deep_workspace_warning_emitted = True
                    warning_event = activity_event_factory(
                        event_type="tool_failed",
                        title="Workspace logging disabled",
                        detail=(
                            "Google Docs/Sheets is not connected. "
                            "Continuing deep research without external notebook sync."
                        ),
                        metadata={
                            "tool_id": shadow_step.tool_id,
                            "step": index,
                            "shadow": True,
                        },
                    )
                    yield emit_event(warning_event)
            shadow_failed = activity_event_factory(
                event_type="tool_failed",
                title=f"Failed: {shadow_step.title}",
                detail=str(shadow_exc),
                metadata={
                    "tool_id": shadow_step.tool_id,
                    "step": index,
                    "shadow": True,
                },
            )
            yield emit_event(shadow_failed)
