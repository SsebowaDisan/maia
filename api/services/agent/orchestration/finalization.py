from __future__ import annotations

import html
import json
import time
from collections.abc import Callable, Generator
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.critic import review_final_answer
from api.services.agent.events import coverage_report
from api.services.agent.intelligence import build_verification_report
from api.services.agent.llm_execution_support import curate_next_steps_for_task
from api.services.agent.llm_response_formatter import polish_final_response
from api.services.agent.models import AgentActivityEvent, AgentRunResult
from api.services.agent.observability import get_agent_observability

from .answer_builder import compose_professional_answer
from .contract_gate import action_rows_for_contract_check, run_contract_check_live
from .models import ExecutionState, TaskPreparation
from .web_evidence import summarize_web_evidence
from .web_kpi import evaluate_web_kpi_gate, summarize_web_kpi


def _source_metadata(source: Any) -> dict[str, Any]:
    payload = getattr(source, "metadata", {})
    return payload if isinstance(payload, dict) else {}


def _source_page_label(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("page_label", "page", "page_number", "page_index"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:24]
    return ""


def _source_extract(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("extract", "excerpt", "snippet", "quote", "text_excerpt", "text"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:1200]
    source_label = " ".join(str(getattr(source, "label", "") or "").split()).strip()
    if source_label and str(getattr(source, "source_type", "") or "").strip().lower() == "web":
        return source_label[:300]
    return ""


def _source_file_id(source: Any) -> str:
    direct = " ".join(str(getattr(source, "file_id", "") or "").split()).strip()
    if direct:
        return direct
    metadata = _source_metadata(source)
    for key in ("file_id", "source_id"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value
    return ""


def _source_highlight_boxes(source: Any) -> list[dict[str, float]]:
    metadata = _source_metadata(source)
    raw = metadata.get("highlight_boxes")
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, float]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x", 0.0))
            y = float(item.get("y", 0.0))
            width = float(item.get("width", 0.0))
            height = float(item.get("height", 0.0))
        except Exception:
            continue
        left = max(0.0, min(1.0, x))
        top = max(0.0, min(1.0, y))
        normalized_width = max(0.0, min(1.0 - left, width))
        normalized_height = max(0.0, min(1.0 - top, height))
        if normalized_width < 0.002 or normalized_height < 0.002:
            continue
        key = (
            round(left, 6),
            round(top, 6),
            round(normalized_width, 6),
            round(normalized_height, 6),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "x": key[0],
                "y": key[1],
                "width": key[2],
                "height": key[3],
            }
        )
        if len(normalized) >= 24:
            break
    return normalized


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
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
    expected_event_types_resolver: Callable[..., list[str]],
) -> Generator[dict[str, Any], None, AgentRunResult]:
    verification_report = build_verification_report(
        task=task_prep.task_intelligence,
        planned_tool_ids=[step.tool_id for step in steps],
        executed_steps=state.executed_steps,
        actions=state.all_actions,
        sources=state.all_sources,
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
        verification_check_event = activity_event_factory(
            event_type="verification_check",
            title=str(check.get("name") or "Verification check"),
            detail=str(check.get("detail") or ""),
            metadata={
                "status": str(check.get("status") or "info"),
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
        minimum_seconds_raw = settings.get("agent.deep_research_min_seconds", 30)
        try:
            minimum_seconds = max(30.0, float(minimum_seconds_raw))
        except Exception:
            minimum_seconds = 30.0
        elapsed_seconds = time.perf_counter() - run_started_clock
        remaining_seconds = minimum_seconds - elapsed_seconds
        if remaining_seconds > 0.4:
            waited = 0.0
            wait_started_event = activity_event_factory(
                event_type="tool_progress",
                title="Running deep research cross-checks",
                detail="Verifying evidence consistency before final synthesis",
                metadata={"step": len(steps), "progress": 0.0},
            )
            yield emit_event(wait_started_event)
            while waited < remaining_seconds:
                chunk = min(2.0, remaining_seconds - waited)
                time.sleep(chunk)
                waited += chunk
                progress = min(1.0, waited / remaining_seconds) if remaining_seconds > 0 else 1.0
                wait_progress_event = activity_event_factory(
                    event_type="tool_progress",
                    title="Deep research quality pass",
                    detail=f"Cross-check in progress ({int(progress * 100)}%)",
                    metadata={"step": len(steps), "progress": round(progress, 3)},
                )
                yield emit_event(wait_progress_event)

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
    final_reason = " ".join(str(state.contract_check_result.get("reason") or "").split()).strip()
    if final_reason:
        state.execution_context.settings["__task_contract_reason"] = final_reason[:320]

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
        sources=state.all_sources,
        next_steps=unique_next_steps,
        runtime_settings=state.execution_context.settings,
        verification_report=verification_report,
    )
    answer = polish_final_response(
        request_message=request.message,
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
        for source in state.all_sources
        if str(source.url or "").strip()
    ]
    critic_result = review_final_answer(
        request_message=request.message,
        answer_text=answer,
        source_urls=source_urls,
    )
    critic_needs_human_review = bool(critic_result.get("needs_human_review"))
    critic_review_notes = " ".join(
        str(critic_result.get("critic_note") or "").split()
    ).strip()[:420]
    barrier_handoff_required = bool(
        state.execution_context.settings.get("__barrier_handoff_required")
    )
    barrier_handoff_note = " ".join(
        str(state.execution_context.settings.get("__barrier_handoff_note") or "").split()
    ).strip()[:420]
    needs_human_review = bool(critic_needs_human_review or barrier_handoff_required)
    human_review_notes = critic_review_notes
    if barrier_handoff_required and barrier_handoff_note:
        if human_review_notes:
            if barrier_handoff_note not in human_review_notes:
                human_review_notes = f"{barrier_handoff_note} | {human_review_notes}"[:420]
        else:
            human_review_notes = barrier_handoff_note

    if needs_human_review and human_review_notes:
        critic_event = activity_event_factory(
            event_type="verification_check",
            title="Human review required" if barrier_handoff_required else "Critic review flagged issues",
            detail=human_review_notes,
            metadata={
                "needs_human_review": True,
                "barrier_handoff_required": barrier_handoff_required,
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
            metadata={"needs_human_review": False},
        )
        yield emit_event(critic_ok_event)

    info_blocks: list[str] = []
    for idx, source in enumerate(state.all_sources, start=1):
        label = html.escape(source.label)
        raw_url = " ".join(str(source.url or "").split()).strip()
        url = html.escape(raw_url)
        page_label = html.escape(_source_page_label(source))
        source_extract = html.escape(_source_extract(source))
        file_id = html.escape(_source_file_id(source), quote=True)
        source_boxes = _source_highlight_boxes(source)
        detail = (
            f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{url}</a>"
            if url
            else "Internal source"
        )
        details_file_attr = f" data-file-id='{file_id}'" if file_id else ""
        details_page_attr = f" data-page='{page_label}'" if page_label else ""
        details_source_url_attr = (
            f" data-source-url='{html.escape(raw_url, quote=True)}'"
            if raw_url.startswith(("http://", "https://"))
            else ""
        )
        details_boxes_attr = (
            f" data-boxes='{html.escape(json.dumps(source_boxes, separators=(',', ':'), ensure_ascii=True), quote=True)}'"
            if source_boxes
            else ""
        )
        extract_block = (
            f"<div class='evidence-content'><b>Extract:</b> {source_extract}</div>"
            if source_extract
            else ""
        )
        info_block = (
            f"<details class='evidence' id='evidence-{idx}'{details_file_attr}{details_source_url_attr}{details_page_attr}{details_boxes_attr} {'open' if idx == 1 else ''}>"
            f"<summary><i>Evidence [{idx}]</i></summary>"
            f"<div><b>Source:</b> [{idx}] {label}</div>"
            f"{extract_block}"
            f"<div class='evidence-content'><b>Link:</b> {detail}</div>"
            "</details>"
        )
        info_blocks.append(
            info_block
        )
    info_html = "".join(info_blocks)

    result = AgentRunResult(
        run_id=run_id,
        answer=answer,
        info_html=info_html,
        actions_taken=state.all_actions,
        sources_used=state.all_sources,
        next_recommended_steps=unique_next_steps[:8],
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
            f"{len(state.all_sources)} source(s)"
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

    activity_store.end_run(run_id, result.to_dict())
    audit.write(
        user_id=user_id,
        tenant_id=access_context.tenant_id,
        run_id=run_id,
        event="agent_run_completed",
        payload={
            "conversation_id": conversation_id,
            "steps": len(steps),
            "actions": len(state.all_actions),
            "sources": len(state.all_sources),
            "event_coverage_percent": coverage.get("coverage_percent", 0),
            "web_ready_for_scale": bool(web_kpi_gate.get("ready_for_scale")),
            "web_steps_total": int(web_kpi_summary.get("web_steps_total") or 0),
            "web_evidence_total": int(web_evidence_summary.get("web_evidence_total") or 0),
        },
    )
    memory.save_run(
        {
            "run_id": run_id,
            "user_id": user_id,
            "tenant_id": access_context.tenant_id,
            "conversation_id": conversation_id,
            "message": request.message,
            "agent_goal": request.agent_goal,
            "answer": result.answer,
            "actions_taken": [item.to_dict() for item in result.actions_taken],
            "sources_used": [item.to_dict() for item in result.sources_used],
            "next_recommended_steps": result.next_recommended_steps,
            "needs_human_review": result.needs_human_review,
            "human_review_notes": result.human_review_notes,
            "web_summary": result.web_summary,
            "user_preferences": task_prep.user_preferences,
            "event_coverage": coverage,
        }
    )
    get_agent_observability().observe_run_completion(
        run_id=run_id,
        step_count=len(steps),
        action_count=len(state.all_actions),
        source_count=len(state.all_sources),
        needs_human_review=result.needs_human_review,
        reward_score=None,
    )
    return result
