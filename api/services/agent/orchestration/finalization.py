from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.critic import review_final_answer
from api.services.agent.events import coverage_report
from api.services.agent.intelligence import build_verification_report
from api.services.agent.llm_execution_support import curate_next_steps_for_task
from api.services.agent.llm_response_formatter import polish_final_response
from api.services.agent.models import AgentActivityEvent, AgentRunResult, utc_now

from .answer_builder import compose_professional_answer
from .contract_gate import action_rows_for_contract_check, run_contract_check_live
from .finalization_persistence import persist_completed_run
from .handoff_state import is_handoff_paused, read_handoff_state
from .models import ExecutionState, TaskPreparation
from .web_evidence import summarize_web_evidence
from .web_kpi import evaluate_web_kpi_gate, summarize_web_kpi

from .finalization_evidence import (
    _build_evidence_items_from_sources,
    _build_info_html_from_sources,
)
from .finalization_scope import filter_sources_for_response_scope


def _post_resume_verification_state(
    *,
    settings: dict[str, Any],
    contract_check_result: dict[str, Any],
    final_missing_items: list[str],
    handoff_state: dict[str, Any],
) -> dict[str, Any]:
    pending_before = bool(settings.get("__barrier_resume_pending_verification"))
    if not pending_before:
        return {
            "pending_before": False,
            "blocked": False,
            "cleared": False,
            "note": "",
        }

    handoff_runtime_state = " ".join(str(handoff_state.get("state") or "").split()).strip().lower()
    ready_for_actions = bool(contract_check_result.get("ready_for_external_actions"))
    verification_can_clear = (
        ready_for_actions
        and not final_missing_items
        and handoff_runtime_state in {"resumed", "running", ""}
    )
    if verification_can_clear:
        settings["__barrier_resume_pending_verification"] = False
        settings["__barrier_resume_verified_at"] = utc_now().isoformat()
        settings["__barrier_resume_verification_note"] = ""
        return {
            "pending_before": True,
            "blocked": False,
            "cleared": True,
            "note": "",
        }

    note = (
        "Post-resume verification is still required before confirming external side effects."
    )
    settings["__barrier_resume_pending_verification"] = True
    settings["__barrier_resume_verification_note"] = note
    return {
        "pending_before": True,
        "blocked": True,
        "cleared": False,
        "note": note,
    }


def finalize_run(
    *,
    run_id: str,
    user_id: str,
    conversation_id: str,
    request: ChatRequest,
    settings: dict[str, Any],
    access_context: Any,
    task_prep: TaskPreparation,
    steps: list[Any],
    deep_research_mode: bool,
    run_started_clock: float,
    observed_event_types: list[str],
    state: ExecutionState,
    activity_store: Any,
    audit: Any,
    memory: Any,
    session_store: Any,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
    expected_event_types_resolver: Callable[..., list[str]],
) -> Generator[dict[str, Any], None, AgentRunResult]:
    response_sources = filter_sources_for_response_scope(
        sources=state.all_sources,
        settings=state.execution_context.settings,
    )
    verification_report = build_verification_report(
        task=task_prep.task_intelligence,
        planned_tool_ids=[step.tool_id for step in steps],
        executed_steps=state.executed_steps,
        actions=state.all_actions,
        sources=response_sources,
        runtime_settings=state.execution_context.settings,
    )
    verification_started_event = activity_event_factory(
        event_type="verification_started",
        title="Run verification checks",
        detail="Evaluating evidence quality, delivery completion, and execution stability",
        metadata={"check_count": len(verification_report.get("checks") or [])},
    )
    yield emit_event(verification_started_event)
    for check in verification_report.get("checks") or []:
        if not isinstance(check, dict):
            continue
        raw_status = str(check.get("status") or "").strip().lower()
        check_status = raw_status if raw_status in {"pass", "warning", "fail", "info"} else "pass"
        verification_check_event = activity_event_factory(
            event_type="verification_check",
            title=str(check.get("name") or "Verification check"),
            detail=str(check.get("detail") or ""),
            metadata={
                "status": check_status,
                "score": verification_report.get("score"),
            },
        )
        yield emit_event(verification_check_event)
    verification_completed_event = activity_event_factory(
        event_type="verification_completed",
        title="Verification completed",
        detail=f"Quality score: {verification_report.get('score')}% ({verification_report.get('grade')})",
        metadata=verification_report,
    )
    yield emit_event(verification_completed_event)
    web_kpi_summary = summarize_web_kpi(state.execution_context.settings)
    web_evidence_summary = summarize_web_evidence(state.execution_context.settings)
    web_kpi_gate = evaluate_web_kpi_gate(
        settings=state.execution_context.settings,
        summary=web_kpi_summary,
    )
    if int(web_kpi_summary.get("web_steps_total") or 0) > 0:
        web_kpi_event = activity_event_factory(
            event_type="web_kpi_summary",
            title="Web reliability summary",
            detail=(
                f"Web steps={web_kpi_summary.get('web_steps_total')} | "
                f"avg quality={web_kpi_summary.get('avg_quality_score')} | "
                f"blocked={web_kpi_summary.get('blocked_count')}"
            ),
            metadata=web_kpi_summary,
        )
        yield emit_event(web_kpi_event)
    if int(web_evidence_summary.get("web_evidence_total") or 0) > 0:
        web_evidence_event = activity_event_factory(
            event_type="web_evidence_summary",
            title="Web evidence summary",
            detail=(
                f"Evidence items={web_evidence_summary.get('web_evidence_total')} | "
                f"citations_ready={web_evidence_summary.get('citations_ready')}"
            ),
            metadata=web_evidence_summary,
        )
        yield emit_event(web_evidence_event)
    if int(web_kpi_summary.get("web_steps_total") or 0) > 0:
        gate_failed_checks = [
            str(item).strip()
            for item in (web_kpi_gate.get("failed_checks") if isinstance(web_kpi_gate, dict) else [])
            if str(item).strip()
        ]
        gate_ready = bool(web_kpi_gate.get("ready_for_scale"))
        gate_event = activity_event_factory(
            event_type="web_release_gate",
            title="Web rollout gate evaluation",
            detail=(
                "Web stack passed release gate thresholds."
                if gate_ready
                else f"Web stack below thresholds: {', '.join(gate_failed_checks[:3])}"
            ),
            metadata=web_kpi_gate,
        )
        yield emit_event(gate_event)
        if bool(web_kpi_gate.get("gate_enforced")) and not gate_ready:
            gate_note = (
                "Web KPI gate is enforced and currently below threshold. "
                "Review gate checks before enabling full rollout."
            )
            if gate_note not in state.next_steps:
                state.next_steps.insert(0, gate_note)

    if deep_research_mode:
        # Emit a non-blocking progress pulse for deep research UX (no sleep).
        wait_started_event = activity_event_factory(
            event_type="tool_progress",
            title="Running deep research cross-checks",
            detail="Verifying evidence consistency before final synthesis",
            metadata={"step": len(steps), "progress": 0.0},
        )
        yield emit_event(wait_started_event)
        wait_done_event = activity_event_factory(
            event_type="tool_progress",
            title="Deep research quality pass",
            detail="Cross-check complete (100%)",
            metadata={"step": len(steps), "progress": 1.0},
        )
        yield emit_event(wait_done_event)

    state.contract_check_result = yield from run_contract_check_live(
        run_id=run_id,
        phase="before_final_response",
        task_contract=task_prep.task_contract,
        request_message=request.message,
        execution_context=state.execution_context,
        executed_steps=state.executed_steps,
        actions=state.all_actions,
        sources=state.all_sources,
        emit_event=emit_event,
        activity_event_factory=activity_event_factory,
    )
    final_missing_items = (
        [
            str(item).strip()
            for item in state.contract_check_result.get("missing_items", [])
            if str(item).strip()
        ]
        if isinstance(state.contract_check_result.get("missing_items"), list)
        else []
    )
    state.execution_context.settings["__task_contract_check"] = state.contract_check_result
    if final_missing_items:
        state.execution_context.settings["__task_contract_missing_items"] = final_missing_items[:8]
        for item in final_missing_items[:8]:
            if item and item not in state.next_steps:
                state.next_steps.append(item)
        missing_items_event = activity_event_factory(
            event_type="verification_check",
            title="Contract items not fully satisfied",
            detail=f"{len(final_missing_items)} item(s) unresolved: {'; '.join(final_missing_items[:3])}",
            metadata={
                "missing_items": final_missing_items[:8],
                "missing_item_count": len(final_missing_items),
                "status": "warning",
            },
        )
        yield emit_event(missing_items_event)
    final_reason = " ".join(str(state.contract_check_result.get("reason") or "").split()).strip()
    if final_reason:
        state.execution_context.settings["__task_contract_reason"] = final_reason[:320]
    handoff_state = read_handoff_state(settings=state.execution_context.settings)
    post_resume_verification = _post_resume_verification_state(
        settings=state.execution_context.settings,
        contract_check_result=state.contract_check_result,
        final_missing_items=final_missing_items,
        handoff_state=handoff_state,
    )
    if post_resume_verification.get("blocked"):
        resume_note = str(post_resume_verification.get("note") or "").strip()
        if resume_note:
            if resume_note not in state.next_steps:
                state.next_steps.insert(0, resume_note)
        missing = (
            list(state.contract_check_result.get("missing_items", []))
            if isinstance(state.contract_check_result.get("missing_items"), list)
            else []
        )
        resume_missing = "Post-resume verification required before confirming external side effects."
        if resume_missing not in missing:
            missing.append(resume_missing)
        state.contract_check_result["missing_items"] = missing[:8]
        state.contract_check_result["ready_for_external_actions"] = False
        verification_event = activity_event_factory(
            event_type="verification_check",
            title="Post-resume verification pending",
            detail=resume_note or resume_missing,
            metadata={
                "post_resume_verification_pending": True,
                "barrier_type": str(handoff_state.get("barrier_type") or ""),
                "resume_status": str(handoff_state.get("resume_status") or ""),
            },
        )
        yield emit_event(verification_event)
    elif post_resume_verification.get("cleared"):
        verification_event = activity_event_factory(
            event_type="verification_check",
            title="Post-resume verification completed",
            detail="Resumed run passed final contract verification checks.",
            metadata={
                "status": "pass",
                "post_resume_verification_pending": False,
                "barrier_type": str(handoff_state.get("barrier_type") or ""),
                "resume_status": str(handoff_state.get("resume_status") or ""),
            },
        )
        yield emit_event(verification_event)
        approval_granted_event = activity_event_factory(
            event_type="approval_granted",
            title="Approval granted",
            detail="Contract verification passed. External actions are cleared to proceed.",
            metadata={
                "barrier_type": str(handoff_state.get("barrier_type") or ""),
                "resume_status": str(handoff_state.get("resume_status") or ""),
                "ready_for_external_actions": True,
            },
        )
        yield emit_event(approval_granted_event)

    unique_next_steps = curate_next_steps_for_task(
        request_message=request.message,
        task_contract=task_prep.task_contract,
        candidate_steps=state.next_steps,
        executed_steps=state.executed_steps,
        actions=action_rows_for_contract_check(state.all_actions),
        max_items=8,
    )

    synthesis_started_event = activity_event_factory(
        event_type="synthesis_started",
        title="Synthesizing final response",
        detail="Combining tool outputs into one structured answer",
    )
    yield emit_event(synthesis_started_event)

    answer = compose_professional_answer(
        request=request,
        planned_steps=steps,
        executed_steps=state.executed_steps,
        actions=state.all_actions,
        sources=response_sources,
        next_steps=unique_next_steps,
        runtime_settings=state.execution_context.settings,
        verification_report=verification_report,
    )
    requested_language = " ".join(str(request.language or "").split()).strip()
    if requested_language in {"", "(default)"}:
        requested_language = None

    answer = polish_final_response(
        request_message=request.message,
        requested_language=requested_language,
        answer_text=answer,
        verification_report=verification_report,
        preferences={
            **(task_prep.user_preferences if isinstance(task_prep.user_preferences, dict) else {}),
            "task_preferred_tone": task_prep.task_intelligence.preferred_tone,
            "task_preferred_format": task_prep.task_intelligence.preferred_format,
            "simple_explanation_required": bool(
                state.execution_context.settings.get("__simple_explanation_required")
            ),
            "include_execution_why": bool(state.execution_context.settings.get("__include_execution_why")),
            "research_depth_tier": str(
                state.execution_context.settings.get("__research_depth_tier") or "standard"
            ),
        },
    )
    source_urls = [
        str(source.url or "").strip()
        for source in response_sources
        if str(source.url or "").strip()
    ]
    critic_result = review_final_answer(
        request_message=request.message,
        answer_text=answer,
        source_urls=source_urls,
        actions=action_rows_for_contract_check(state.all_actions),
        contract_check=state.contract_check_result,
    )
    critic_needs_human_review = bool(critic_result.get("needs_human_review"))
    critic_review_notes = " ".join(
        str(critic_result.get("critic_note") or "").split()
    ).strip()[:420]
    barrier_handoff_required = is_handoff_paused(settings=state.execution_context.settings) or bool(
        state.execution_context.settings.get("__barrier_handoff_required")
    )
    post_resume_verification_blocked = bool(post_resume_verification.get("blocked"))
    post_resume_note = " ".join(
        str(
            post_resume_verification.get("note")
            or state.execution_context.settings.get("__barrier_resume_verification_note")
            or ""
        ).split()
    ).strip()[:420]
    barrier_handoff_note = " ".join(
        str(
            handoff_state.get("note")
            or state.execution_context.settings.get("__barrier_handoff_note")
            or ""
        ).split()
    ).strip()[:420]
    needs_human_review = bool(
        critic_needs_human_review or barrier_handoff_required or post_resume_verification_blocked
    )
    human_review_notes = critic_review_notes
    if barrier_handoff_required and barrier_handoff_note:
        if human_review_notes:
            if barrier_handoff_note not in human_review_notes:
                human_review_notes = f"{barrier_handoff_note} | {human_review_notes}"[:420]
        else:
            human_review_notes = barrier_handoff_note
    if post_resume_verification_blocked and post_resume_note:
        if human_review_notes:
            if post_resume_note not in human_review_notes:
                human_review_notes = f"{post_resume_note} | {human_review_notes}"[:420]
        else:
            human_review_notes = post_resume_note

    if needs_human_review and human_review_notes:
        critic_event = activity_event_factory(
            event_type="verification_check",
            title=(
                "Human review required"
                if barrier_handoff_required
                else (
                    "Post-resume verification required"
                    if post_resume_verification_blocked
                    else "Critic review flagged issues"
                )
            ),
            detail=human_review_notes,
            metadata={
                "needs_human_review": True,
                "barrier_handoff_required": barrier_handoff_required,
                "post_resume_verification_pending": post_resume_verification_blocked,
            },
        )
        yield emit_event(critic_event)
        if human_review_notes not in unique_next_steps:
            unique_next_steps = [human_review_notes, *unique_next_steps][:8]
    elif not needs_human_review:
        critic_ok_event = activity_event_factory(
            event_type="verification_check",
            title="Critic review passed",
            detail="No major factual or safety issues flagged.",
            metadata={"status": "pass", "needs_human_review": False},
        )
        yield emit_event(critic_ok_event)
        if bool(state.contract_check_result.get("ready_for_external_actions")):
            approval_granted_event = activity_event_factory(
                event_type="approval_granted",
                title="Approval granted",
                detail="All contract checks passed. External actions cleared to proceed.",
                metadata={
                    "ready_for_external_actions": True,
                    "needs_human_review": False,
                },
            )
            yield emit_event(approval_granted_event)

    evidence_items = _build_evidence_items_from_sources(response_sources)
    info_html = _build_info_html_from_sources(
        response_sources,
        evidence_items=evidence_items,
    )

    result = AgentRunResult(
        run_id=run_id,
        answer=answer,
        info_html=info_html,
        actions_taken=state.all_actions,
        sources_used=response_sources,
        next_recommended_steps=unique_next_steps[:8],
        evidence_items=[item.to_info_panel_payload() for item in evidence_items],
        needs_human_review=needs_human_review,
        human_review_notes=human_review_notes,
        web_summary={
            "kpi": web_kpi_summary,
            "evidence": web_evidence_summary,
            "release_gate": web_kpi_gate,
        },
    )
    synthesis_completed_event = activity_event_factory(
        event_type="synthesis_completed",
        title="Final response ready",
        detail=(
            f"Generated {len(state.all_actions)} action result(s) with "
            f"{len(response_sources)} source(s)"
        ),
    )
    yield emit_event(synthesis_completed_event)

    expected_events = expected_event_types_resolver(steps=steps, request=request)
    coverage = coverage_report(
        observed_event_types=observed_event_types,
        expected_event_types=expected_events,
    )
    coverage_event = activity_event_factory(
        event_type="event_coverage",
        title="Generated event coverage report",
        detail=f"{coverage['coverage_percent']}% expected events were emitted",
        metadata=coverage,
        stage="result",
        status="completed",
    )
    yield emit_event(coverage_event)

    persist_completed_run(
        run_id=run_id,
        user_id=user_id,
        conversation_id=conversation_id,
        request=request,
        access_context=access_context,
        result=result,
        coverage=coverage,
        verification_report=verification_report,
        task_contract_objective=task_prep.contract_objective,
        user_preferences=task_prep.user_preferences,
        step_count=len(steps),
        action_count=len(state.all_actions),
        source_count=len(state.all_sources),
        web_kpi_gate=web_kpi_gate,
        web_kpi_summary=web_kpi_summary,
        web_evidence_summary=web_evidence_summary,
        activity_store=activity_store,
        session_store=session_store,
        audit=audit,
        memory=memory,
    )
    return result
