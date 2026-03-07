from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Callable, Generator
from typing import Any
from urllib.parse import urlparse

from api.schemas import ChatRequest
from api.services.agent.critic import review_final_answer
from api.services.agent.events import coverage_report
from api.services.agent.intelligence import build_verification_report
from api.services.agent.llm_execution_support import curate_next_steps_for_task
from api.services.agent.llm_response_formatter import polish_final_response
from api.services.agent.models import AgentActivityEvent, AgentRunResult, utc_now
from api.services.agent.observability import get_agent_observability

from .answer_builder import compose_professional_answer
from .contract_gate import action_rows_for_contract_check, run_contract_check_live
from .handoff_state import is_handoff_paused, read_handoff_state
from .models import ExecutionState, TaskPreparation
from .web_evidence import summarize_web_evidence
from .web_kpi import evaluate_web_kpi_gate, summarize_web_kpi

_ARTIFACT_URL_PATH_SEGMENTS = {
    "extract",
    "source",
    "link",
    "evidence",
    "citation",
    "title",
    "markdown",
    "content",
    "published",
    "time",
    "url",
}


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


def _compact_text(value: str, *, max_chars: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped.strip()}..."


def _normalize_source_url(raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").split()).strip()
    if not value:
        return ""
    if len(value) > 2048:
        value = value[:2048]
    value = value.strip(" <>\"'`")
    value = value.rstrip(".,;:!?")
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path_segments = [
        segment.strip().lower()
        for segment in str(parsed.path or "").split("/")
        if segment.strip()
    ]
    if len(path_segments) == 1 and path_segments[0].rstrip(":") in _ARTIFACT_URL_PATH_SEGMENTS:
        return ""
    return parsed.geturl()


def _clean_source_label(raw_value: Any) -> str:
    text = " ".join(str(raw_value or "").split()).strip()
    if not text:
        return ""
    text = re.sub(r"\bURL\s*Source\s*:\s*https?://[^\s<>'\")\]]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPublished\s*Time\s*:\s*[^|]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMarkdown\s*Content\s*:\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" |:-")
    return _compact_text(text, max_chars=180)


def _source_extract(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("extract", "excerpt", "snippet", "quote", "text_excerpt", "text"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return _compact_text(value, max_chars=1200)
    source_label = _clean_source_label(getattr(source, "label", ""))
    source_type = str(getattr(source, "source_type", "") or "").strip().lower()
    if source_label and source_type in {"file", "document", "pdf"}:
        return _compact_text(source_label, max_chars=260)
    return ""


def _source_url(source: Any) -> str:
    metadata = _source_metadata(source)
    label = " ".join(str(getattr(source, "label", "") or "").split()).strip()
    url_candidates = [
        getattr(source, "url", ""),
        metadata.get("source_url"),
        metadata.get("page_url"),
        metadata.get("url"),
        metadata.get("link"),
        label if label.lower().startswith(("http://", "https://")) else "",
    ]
    for candidate in url_candidates:
        normalized = _normalize_source_url(candidate)
        if normalized:
            return normalized
    return ""


def _source_display_label(source: Any, *, source_url: str, fallback_id: int) -> str:
    label = _clean_source_label(getattr(source, "label", ""))
    if label and not label.lower().startswith(("http://", "https://")):
        return label
    if source_url:
        return source_url
    return f"Indexed source {fallback_id}"


def _source_match_quality(source: Any) -> str:
    metadata = _source_metadata(source)
    raw = " ".join(str(metadata.get("match_quality") or "").split()).strip().lower()
    if not raw:
        return ""
    return raw[:32]


def _source_unit_id(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("unit_id", "chunk_id", "span_id"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:160]
    return ""


def _source_char_span(source: Any) -> tuple[int, int]:
    metadata = _source_metadata(source)
    try:
        char_start = int(metadata.get("char_start", 0) or 0)
    except Exception:
        char_start = 0
    try:
        char_end = int(metadata.get("char_end", 0) or 0)
    except Exception:
        char_end = 0
    if char_start <= 0 or char_end <= char_start:
        return 0, 0
    return char_start, char_end


def _source_strength_score(source: Any) -> float:
    metadata = _source_metadata(source)
    for key in ("strength_score", "score"):
        try:
            value = float(metadata.get(key, 0.0) or 0.0)
        except Exception:
            continue
        if value > 0:
            return max(0.0, min(1.0, value))
    return 0.0


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


def _host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


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


def _filter_sources_for_response_scope(
    *,
    sources: list[Any],
    settings: dict[str, Any],
) -> list[Any]:
    target_url = " ".join(str(settings.get("__task_target_url") or "").split()).strip()
    target_host = _host_from_url(target_url)
    if not target_host:
        return sources
    scoped = [
        source
        for source in sources
        if not str(getattr(source, "url", "") or "").strip()
        or (
            _host_from_url(str(getattr(source, "url", "") or "").strip()) == target_host
            or _host_from_url(str(getattr(source, "url", "") or "").strip()).endswith(f".{target_host}")
        )
    ]
    return scoped if scoped else sources


def _strength_tier_from_score(strength_score: float) -> int:
    if strength_score >= 0.7:
        return 3
    if strength_score >= 0.42:
        return 2
    return 1


def _build_info_html_from_sources(response_sources: list[Any]) -> str:
    if not response_sources:
        return ""
    info_blocks: list[str] = ["<div class='evidence-list' data-layout='kotaemon'>"]
    for idx, source in enumerate(response_sources, start=1):
        source_url = _source_url(source)
        source_label = _source_display_label(source, source_url=source_url, fallback_id=idx)
        page_label = _source_page_label(source)
        source_extract = _source_extract(source)
        file_id = _source_file_id(source)
        source_boxes = _source_highlight_boxes(source)
        source_unit_id = _source_unit_id(source)
        source_match_quality = _source_match_quality(source)
        char_start, char_end = _source_char_span(source)
        strength_score = _source_strength_score(source)
        strength_tier = _strength_tier_from_score(strength_score) if strength_score > 0 else 0

        summary_label = f"Evidence [{idx}]"
        if page_label:
            summary_label += f" - page {page_label}"

        details_attrs = [f"class='evidence'", f"id='evidence-{idx}'", f"data-evidence-id='evidence-{idx}'"]
        if file_id:
            details_attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if page_label:
            details_attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
        if source_url:
            details_attrs.append(f"data-source-url='{html.escape(source_url, quote=True)}'")
        if source_unit_id:
            details_attrs.append(f"data-unit-id='{html.escape(source_unit_id, quote=True)}'")
        if source_match_quality:
            details_attrs.append(f"data-match-quality='{html.escape(source_match_quality, quote=True)}'")
        if char_start > 0:
            details_attrs.append(f"data-char-start='{char_start}'")
        if char_end > char_start:
            details_attrs.append(f"data-char-end='{char_end}'")
        if strength_score > 0:
            details_attrs.append(f"data-strength='{strength_score:.6f}'")
            details_attrs.append(f"data-strength-tier='{strength_tier}'")
        if source_boxes:
            details_attrs.append(
                "data-boxes='"
                + html.escape(
                    json.dumps(source_boxes, separators=(",", ":"), ensure_ascii=True),
                    quote=True,
                )
                + "'"
            )
        if idx == 1:
            details_attrs.append("open")

        if source_url:
            source_label_block = (
                f"<a href='{html.escape(source_url, quote=True)}' target='_blank' rel='noopener noreferrer'>"
                f"{html.escape(source_label)}"
                "</a>"
            )
            link_block = (
                "<div class='evidence-content'><b>Link:</b> "
                f"<a href='{html.escape(source_url, quote=True)}' target='_blank' rel='noopener noreferrer'>"
                f"{html.escape(source_url)}"
                "</a></div>"
            )
        else:
            source_label_block = html.escape(source_label)
            link_block = ""

        extract_block = (
            f"<div class='evidence-content'><b>Extract:</b> {html.escape(source_extract)}</div>"
            if source_extract
            else ""
        )
        info_block = (
            f"<details {' '.join(details_attrs)}>"
            f"<summary>{html.escape(summary_label)}</summary>"
            f"<div><b>Source:</b> [{idx}] {source_label_block}</div>"
            f"{extract_block}"
            f"{link_block}"
            "</details>"
        )
        info_blocks.append(info_block)
    info_blocks.append("</div>")
    return "".join(info_blocks)


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
    response_sources = _filter_sources_for_response_scope(
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
                "post_resume_verification_pending": False,
                "barrier_type": str(handoff_state.get("barrier_type") or ""),
                "resume_status": str(handoff_state.get("resume_status") or ""),
            },
        )
        yield emit_event(verification_event)

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
            metadata={"needs_human_review": False},
        )
        yield emit_event(critic_ok_event)

    info_html = _build_info_html_from_sources(response_sources)

    result = AgentRunResult(
        run_id=run_id,
        answer=answer,
        info_html=info_html,
        actions_taken=state.all_actions,
        sources_used=response_sources,
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

    activity_store.end_run(run_id, result.to_dict())
    try:
        session_store.save_session_run(
            {
                "run_id": run_id,
                "user_id": user_id,
                "tenant_id": access_context.tenant_id,
                "conversation_id": conversation_id,
                "message": request.message,
                "agent_goal": request.agent_goal,
                "answer": result.answer,
                "next_recommended_steps": result.next_recommended_steps,
                "needs_human_review": result.needs_human_review,
                "human_review_notes": result.human_review_notes,
                "event_coverage": coverage,
                "verification_grade": verification_report.get("grade"),
                "verification_score": verification_report.get("score"),
                "task_contract_objective": task_prep.contract_objective,
            }
        )
    except Exception:
        pass
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
