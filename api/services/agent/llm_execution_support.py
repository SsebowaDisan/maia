"""Compatibility shim for LLM execution helpers.

Deprecated module path for implementation details:
- use `api.services.agent.llm_execution_support_parts` for new code.

Compatibility note:
- tests and legacy callers monkeypatch `call_json_response` on this module.
- implementation now lives in multiple submodules that import
  `call_json_response` directly from `llm_runtime`.
- this shim synchronizes the patched callable into those submodules before
  each call so existing monkeypatch behavior continues to work.
"""

from __future__ import annotations

from typing import Any

from api.services.agent.llm_runtime import call_json_response as _runtime_call_json_response

from .llm_execution_support_parts import (
    location_brief as _location_brief_module,
    next_steps as _next_steps_module,
    polishing as _polishing_module,
    recovery as _recovery_module,
    rewriting as _rewriting_module,
    summarization as _summarization_module,
)

call_json_response = _runtime_call_json_response


def _sync_call_json_response() -> None:
    patched = call_json_response
    for module in (
        _location_brief_module,
        _next_steps_module,
        _polishing_module,
        _recovery_module,
        _rewriting_module,
        _summarization_module,
    ):
        if getattr(module, "call_json_response", None) is not patched:
            setattr(module, "call_json_response", patched)


def build_location_delivery_brief(
    *,
    request_message: str,
    objective: str,
    report_body: str,
    browser_findings: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _sync_call_json_response()
    return _location_brief_module.build_location_delivery_brief(
        request_message=request_message,
        objective=objective,
        report_body=report_body,
        browser_findings=browser_findings,
        sources=sources,
    )


def draft_delivery_report_content(
    *,
    request_message: str,
    objective: str,
    report_title: str,
    executed_steps: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    preferred_tone: str = "",
) -> dict[str, str]:
    _sync_call_json_response()
    return _polishing_module.draft_delivery_report_content(
        request_message=request_message,
        objective=objective,
        report_title=report_title,
        executed_steps=executed_steps,
        sources=sources,
        preferred_tone=preferred_tone,
    )


def curate_next_steps_for_task(
    *,
    request_message: str,
    task_contract: dict[str, Any] | None,
    candidate_steps: list[str],
    executed_steps: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    max_items: int = 8,
) -> list[str]:
    _sync_call_json_response()
    return _next_steps_module.curate_next_steps_for_task(
        request_message=request_message,
        task_contract=task_contract,
        candidate_steps=candidate_steps,
        executed_steps=executed_steps,
        actions=actions,
        max_items=max_items,
    )


def polish_contact_form_content(
    *,
    subject: str,
    message_text: str,
    website_url: str,
    context_summary: str = "",
) -> dict[str, str]:
    _sync_call_json_response()
    return _polishing_module.polish_contact_form_content(
        subject=subject,
        message_text=message_text,
        website_url=website_url,
        context_summary=context_summary,
    )


def polish_email_content(
    *,
    subject: str,
    body_text: str,
    recipient: str,
    context_summary: str = "",
    target_format: str = "report_markdown",
) -> dict[str, str]:
    _sync_call_json_response()
    return _polishing_module.polish_email_content(
        subject=subject,
        body_text=body_text,
        recipient=recipient,
        context_summary=context_summary,
        target_format=target_format,
    )


def rewrite_task_for_execution(
    *,
    message: str,
    agent_goal: str | None = None,
    conversation_summary: str = "",
) -> dict[str, Any]:
    _sync_call_json_response()
    return _rewriting_module.rewrite_task_for_execution(
        message=message,
        agent_goal=agent_goal,
        conversation_summary=conversation_summary,
    )


def suggest_failure_recovery(
    *,
    request_message: str,
    tool_id: str,
    step_title: str,
    error_text: str,
    recent_steps: list[dict[str, Any]],
) -> str:
    _sync_call_json_response()
    return _recovery_module.suggest_failure_recovery(
        request_message=request_message,
        tool_id=tool_id,
        step_title=step_title,
        error_text=error_text,
        recent_steps=recent_steps,
    )


def summarize_conversation_window(
    *,
    latest_user_message: str,
    turns: list[dict[str, str]],
) -> str:
    _sync_call_json_response()
    return _summarization_module.summarize_conversation_window(
        latest_user_message=latest_user_message,
        turns=turns,
    )


def summarize_step_outcome(
    *,
    request_message: str,
    tool_id: str,
    step_title: str,
    result_summary: str,
    result_data: dict[str, Any] | None = None,
) -> dict[str, str]:
    _sync_call_json_response()
    return _summarization_module.summarize_step_outcome(
        request_message=request_message,
        tool_id=tool_id,
        step_title=step_title,
        result_summary=result_summary,
        result_data=result_data,
    )


__all__ = [
    "build_location_delivery_brief",
    "call_json_response",
    "curate_next_steps_for_task",
    "draft_delivery_report_content",
    "polish_contact_form_content",
    "polish_email_content",
    "rewrite_task_for_execution",
    "suggest_failure_recovery",
    "summarize_conversation_window",
    "summarize_step_outcome",
]
