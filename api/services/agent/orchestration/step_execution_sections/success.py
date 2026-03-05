from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.llm_execution_support import summarize_step_outcome
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep, build_browser_followup_steps

from ..models import ExecutionState
from ..text_helpers import extract_action_artifact_metadata
from ..web_evidence import record_web_evidence
from ..web_kpi import is_web_tool, record_web_kpi
from .workspace_shadow import run_workspace_shadow_logging


def handle_step_success(
    *,
    access_context: Any,
    deep_research_mode: bool,
    execution_prompt: str,
    state: ExecutionState,
    registry: Any,
    steps: list[PlannedStep],
    step_cursor: int,
    step: PlannedStep,
    index: int,
    step_started: str,
    duration_seconds: float,
    result: Any,
    run_tool_live: Callable[..., Generator[dict[str, Any], None, Any]],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    if is_web_tool(step.tool_id):
        record_web_kpi(
            settings=state.execution_context.settings,
            tool_id=step.tool_id,
            status="success",
            duration_seconds=duration_seconds,
            data=result.data if isinstance(result.data, dict) else {},
        )
        record_web_evidence(
            settings=state.execution_context.settings,
            tool_id=step.tool_id,
            status="success",
            data=result.data if isinstance(result.data, dict) else {},
            sources=result.sources if isinstance(result.sources, list) else [],
        )
    action_metadata = extract_action_artifact_metadata(result.data, step=index)
    action = registry.get(step.tool_id).to_action(
        status="success",
        summary=result.summary,
        started_at=step_started,
        metadata=action_metadata,
    )
    state.all_actions.append(action)
    state.all_sources.extend(result.sources)
    state.executed_steps.append(
        {
            "step": index,
            "tool_id": step.tool_id,
            "title": step.title,
            "status": "success",
            "summary": result.summary,
        }
    )
    llm_step = summarize_step_outcome(
        request_message=execution_prompt,
        tool_id=step.tool_id,
        step_title=step.title,
        result_summary=result.summary,
        result_data=result.data if isinstance(result.data, dict) else {},
    )
    llm_step_summary = str(llm_step.get("summary") or "").strip()
    llm_step_suggestion = str(llm_step.get("suggestion") or "").strip()
    if llm_step_suggestion and llm_step_suggestion not in state.next_steps:
        state.next_steps.append(llm_step_suggestion)
        suggestion_event = activity_event_factory(
            event_type="tool_progress",
            title="LLM context suggestion",
            detail=llm_step_suggestion,
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "llm_suggestion": True,
            },
        )
        yield emit_event(suggestion_event)
    if llm_step_summary:
        llm_step_event = activity_event_factory(
            event_type="llm.step_summary",
            title="LLM step summary",
            detail=llm_step_summary,
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(llm_step_event)
    completed_event = activity_event_factory(
        event_type="tool_completed",
        title=step.title,
        detail=llm_step_summary or result.summary,
        metadata={
            "tool_id": step.tool_id,
            "step": index,
            "llm_step_summary": llm_step_summary,
            "llm_step_suggestion": llm_step_suggestion,
        },
    )
    yield emit_event(completed_event)

    if step.tool_id == "marketing.web_research" and not state.dynamic_inspection_inserted:
        followup_steps = build_browser_followup_steps(
            result.data,
            max_urls=4 if deep_research_mode else 2,
        )
        if followup_steps:
            insertion_point = step_cursor + 1
            steps[insertion_point:insertion_point] = followup_steps
            state.dynamic_inspection_inserted = True
            refined_event = activity_event_factory(
                event_type="plan_refined",
                title="Expanded research plan with live source inspections",
                detail=f"Inserted {len(followup_steps)} source inspection step(s)",
                metadata={
                    "inserted": len(followup_steps),
                    "total_steps": len(steps),
                    "step_ids": [item.tool_id for item in steps],
                },
            )
            yield emit_event(refined_event)

    yield from run_workspace_shadow_logging(
        access_context=access_context,
        execution_prompt=execution_prompt,
        state=state,
        step=step,
        index=index,
        result=result,
        registry=registry,
        run_tool_live=run_tool_live,
        emit_event=emit_event,
        activity_event_factory=activity_event_factory,
    )
