"""Workflow execution engine split into small section modules.

This facade keeps the historic import surface stable while the implementation
lives in focused modules under ``workflow_executor_sections``.
"""
from __future__ import annotations

import sys
import time
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowDefinitionSchema, WorkflowEdge, WorkflowStep
from api.services.mailer_service import send_report_email
from api.services.agents.workflow_executor_sections import activity as _activity_impl
from api.services.agents.workflow_executor_sections import agent_runtime as _agent_impl
from api.services.agents.workflow_executor_sections import delivery as _delivery_impl
from api.services.agents.workflow_executor_sections import dialogue as _dialogue_impl
from api.services.agents.workflow_executor_sections import execution as _execution_impl
from api.services.agents.workflow_executor_sections import review as _review_impl
from api.services.agents.workflow_executor_sections.common import (
    WorkflowExecutionError,
    _clean_stage_topic,
    _count_inline_citation_markers,
    _EMAIL_RE,
    _EMAIL_SUBJECT_RE,
    _EMAIL_TO_RE,
    _emit,
    _eval_condition,
    _extract_email_from_text,
    _extract_terminal_citation_section,
    _format_inputs,
    _has_strong_citation_scaffold,
    _has_terminal_citation_section,
    _INLINE_CITATION_RE,
    _is_search_like_url,
    _looks_like_customer_facing_output,
    _looks_like_email_draft,
    _normalize_delivery_artifact,
    _normalize_http_url,
    _preferred_artifact_keys,
    _SEARCH_HOSTS,
    _step_tool_ids,
    logger,
)

_choose_delivery_artifact = _delivery_impl._choose_delivery_artifact
_derive_delivery_subject = _delivery_impl._derive_delivery_subject
_derive_grounded_email_subject = _delivery_impl._derive_grounded_email_subject
_derive_delivery_body = _delivery_impl._derive_delivery_body
_normalize_grounded_email_result = _delivery_impl._normalize_grounded_email_result
_is_valid_grounded_email_draft = _delivery_impl._is_valid_grounded_email_draft
_is_direct_delivery_candidate = _delivery_impl._is_direct_delivery_candidate
_is_grounded_email_draft_candidate = _delivery_impl._is_grounded_email_draft_candidate
_collect_step_activity_source_urls = _activity_impl._collect_step_activity_source_urls
_append_activity_citation_section = _activity_impl._append_activity_citation_section
_normalize_child_activity_event = _activity_impl._normalize_child_activity_event
_persist_parent_activity_event = _activity_impl._persist_parent_activity_event
_emit_parent_step_event = _activity_impl._emit_parent_step_event
_build_parallel_batches = _execution_impl._build_parallel_batches
_check_conditions = _execution_impl._check_conditions
_validate_output = _execution_impl._validate_output
_validate_stage_contract = _execution_impl._validate_stage_contract
_run_quality_gate = _execution_impl._run_quality_gate
_emit_step_kickoff_chat = _execution_impl._emit_step_kickoff_chat
_rewrite_stage_output_with_llm = _review_impl._rewrite_stage_output_with_llm
_is_compact_research_brief_step = _review_impl._is_compact_research_brief_step
_should_compact_research_brief = _review_impl._should_compact_research_brief
_normalize_numbered_citation_section = _review_impl._normalize_numbered_citation_section
_is_citation_hygiene_dialogue = _review_impl._is_citation_hygiene_dialogue
_should_skip_dialogue_need_for_reviewed_output = _review_impl._should_skip_dialogue_need_for_reviewed_output
_is_safe_integrated_output = _review_impl._is_safe_integrated_output
_review_exhausted_without_proceed = _review_impl._review_exhausted_without_proceed
_normalize_dialogue_turn_type = _dialogue_impl._normalize_dialogue_turn_type
_derive_response_turn_type = _dialogue_impl._derive_response_turn_type
_default_interaction_label = _dialogue_impl._default_interaction_label
_normalize_dialogue_scene_family = _dialogue_impl._normalize_dialogue_scene_family
_normalize_dialogue_scene_surface = _dialogue_impl._normalize_dialogue_scene_surface
_dialogue_action_for_surface = _dialogue_impl._dialogue_action_for_surface
_build_dialogue_prompt_preamble = _dialogue_impl._build_dialogue_prompt_preamble
_record_failure_lesson = _agent_impl._record_failure_lesson
_ensure_supervisor_in_roster = _agent_impl._ensure_supervisor_in_roster
_inject_evolution_overlay = _agent_impl._inject_evolution_overlay
_verify_and_clean_citations = _agent_impl._verify_and_clean_citations
_inject_handoff_context = _agent_impl._inject_handoff_context
_resolve_inputs = _agent_impl._resolve_inputs


def execute_workflow(
    workflow: WorkflowDefinitionSchema,
    tenant_id: str,
    *,
    initial_inputs: dict[str, Any] | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    run_id: str | None = None,
    step_timeout_s: int = 300,
) -> dict[str, Any]:
    return _execution_impl.execute_workflow(
        workflow,
        tenant_id,
        initial_inputs=initial_inputs,
        on_event=on_event,
        run_id=run_id,
        step_timeout_s=step_timeout_s,
        ops=sys.modules[__name__],
    )


def _execute_batch(*args, **kwargs):
    return _execution_impl._execute_batch(*args, **kwargs, ops=sys.modules[__name__])


def _execute_step(*args, **kwargs):
    return _execution_impl._execute_step(*args, **kwargs, ops=sys.modules[__name__])


def _run_direct_delivery_step(*, step: WorkflowStep, step_inputs: dict[str, Any], tenant_id: str, run_id: str, agent_id: str, on_event: Optional[Callable] = None) -> str | None:
    return _delivery_impl._run_direct_delivery_step(step=step, step_inputs=step_inputs, tenant_id=tenant_id, run_id=run_id, agent_id=agent_id, on_event=on_event, ops=sys.modules[__name__])


def _run_grounded_email_draft_step(*, step: WorkflowStep, step_inputs: dict[str, Any], tenant_id: str, run_id: str, on_event: Optional[Callable] = None) -> str:
    return _delivery_impl._run_grounded_email_draft_step(step=step, step_inputs=step_inputs, tenant_id=tenant_id, run_id=run_id, on_event=on_event, ops=sys.modules[__name__])


def _compact_research_brief_output(*, step: WorkflowStep | None, step_inputs: dict[str, Any], result: Any, tenant_id: str) -> Any:
    return _review_impl._compact_research_brief_output(step=step, step_inputs=step_inputs, result=result, tenant_id=tenant_id, ops=sys.modules[__name__])


def _seconds_until_deadline(step_deadline_ts: float | None) -> float | None:
    return _review_impl._seconds_until_deadline(step_deadline_ts, now_fn=time.monotonic)


def _should_skip_post_review_collaboration(*, step_deadline_ts: float | None, minimum_seconds_required: float) -> bool:
    return _review_impl._should_skip_post_review_collaboration(step_deadline_ts=step_deadline_ts, minimum_seconds_required=minimum_seconds_required, now_fn=time.monotonic)


def _run_brain_review(step: WorkflowStep, result: Any, step_inputs: dict[str, Any], tenant_id: str, run_id: str, on_event: Optional[Callable], step_deadline_ts: float | None = None) -> Any:
    return _review_impl._run_brain_review(step=step, result=result, step_inputs=step_inputs, tenant_id=tenant_id, run_id=run_id, on_event=on_event, step_deadline_ts=step_deadline_ts, ops=sys.modules[__name__])


def _run_dialogue_detection(step: WorkflowStep, output: str, tenant_id: str, run_id: str, on_event: Optional[Callable], run_agent_for_agent_fn: Optional[Callable[[str, str], str]] = None) -> str:
    return _dialogue_impl._run_dialogue_detection(step=step, output=output, tenant_id=tenant_id, run_id=run_id, on_event=on_event, run_agent_for_agent_fn=run_agent_for_agent_fn)


def _run_step_with_retry(step: WorkflowStep, step_inputs: dict[str, Any], tenant_id: str, workflow_id: str, run_id: str, on_event: Optional[Callable] = None, step_timeout_s: int | None = None) -> Any:
    return _agent_impl._run_step_with_retry(step, step_inputs, tenant_id, workflow_id, run_id, on_event=on_event, step_timeout_s=step_timeout_s, ops=sys.modules[__name__])


def _dispatch_step(step: WorkflowStep, step_inputs: dict[str, Any], tenant_id: str, run_id: str, on_event: Optional[Callable] = None) -> Any:
    return _agent_impl._dispatch_step(step, step_inputs, tenant_id, run_id, on_event=on_event, ops=sys.modules[__name__])


def _run_agent_step(agent_id: str, step_inputs: dict[str, Any], tenant_id: str, run_id: str = "", on_event: Optional[Callable] = None, step: WorkflowStep | None = None) -> Any:
    return _agent_impl._run_agent_step(agent_id, step_inputs, tenant_id, run_id=run_id, on_event=on_event, step=step, ops=sys.modules[__name__])


class WorkflowExecutor:
    @staticmethod
    def execute_workflow(*args, **kwargs):
        return execute_workflow(*args, **kwargs)


def handle_run_step(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "delegated", "step_id": payload.get("step_id")}
