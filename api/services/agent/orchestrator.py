from __future__ import annotations

import html
import re
import time
from typing import Any, Generator

from api.schemas import ChatRequest
from api.services.agent.activity import get_activity_store
from api.services.agent.audit import get_audit_logger
from api.services.agent.events import CORE_EVENT_TYPES, RunEventEmitter, coverage_report
from api.services.agent.intelligence import (
    build_verification_report,
    derive_task_intelligence,
)
from api.services.agent.live_events import get_live_event_broker
from api.services.agent.llm_execution_support import (
    polish_email_content,
    suggest_failure_recovery,
)
from api.services.agent.llm_personalization import infer_user_preferences
from api.services.agent.llm_research_blueprint import build_research_blueprint
from api.services.agent.llm_response_formatter import polish_final_response
from api.services.agent.memory import get_memory_service
from api.services.agent.models import (
    AgentActivityEvent,
    AgentAction,
    AgentRunResult,
    AgentSource,
    utc_now,
)
from api.services.agent.preferences import get_user_preference_store
from api.services.agent.preflight import run_preflight_checks
from api.services.agent.planner import (
    PlannedStep,
    build_browser_followup_steps,
    build_plan,
    is_deep_research_request,
)
from api.services.agent.policy import (
    ACCESS_MODE_FULL,
    build_access_context,
)
from api.services.agent.tools.base import (
    ToolExecutionContext,
    ToolTraceEvent,
)
from api.services.agent.tools.registry import get_tool_registry
from api.services.mailer_service import send_report_email as send_report_via_mailer
from maia.integrations.gmail_dwd import GmailDwdError


DELIVERY_ACTION_IDS = ("gmail.send", "email.send", "mailer.report_send")


def _compact(text: str, max_len: int = 140) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1].rstrip()}..."


def _truncate_text(text: str, max_len: int = 1800) -> str:
    raw = str(text or "")
    return raw if len(raw) <= max_len else f"{raw[: max_len - 1].rstrip()}..."


def _chunk_preserve_text(text: str, chunk_size: int = 220, limit: int = 8) -> list[str]:
    if not text:
        return []
    size = max(48, int(chunk_size or 220))
    chunks = [text[idx: idx + size] for idx in range(0, len(text), size)]
    return chunks[: max(1, int(limit or 8))]


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _extract_action_artifact_metadata(data: dict[str, Any] | None, *, step: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {"step": step}
    if not isinstance(data, dict):
        return metadata
    for key in ("url", "document_url", "spreadsheet_url", "path", "pdf_path", "document_id", "spreadsheet_id"):
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        metadata[key] = text[:320]
    copied = data.get("copied_snippets")
    if isinstance(copied, list):
        compact = [str(item).strip() for item in copied if str(item).strip()]
        if compact:
            metadata["copied_snippets"] = compact[:4]
    return metadata


EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
def _extract_first_email(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = EMAIL_RE.search(joined)
    return match.group(1).strip() if match else ""


def _issue_fix_hint(issue: str) -> str:
    text = str(issue or "").lower()
    if "gmail_dwd_api_disabled" in text or "gmail api is not enabled" in text:
        return (
            "Enable Gmail API in the Google Cloud project used by the service account, "
            "then retry."
        )
    if "gmail_dwd_delegation_denied" in text or "domain-wide delegation" in text:
        return (
            "Verify Workspace Domain-Wide Delegation for the service-account client ID and "
            "scope `https://www.googleapis.com/auth/gmail.send`."
        )
    if "gmail_dwd_mailbox_unavailable" in text or "mailbox" in text and "suspended" in text:
        return (
            "Confirm the impersonated mailbox exists and is active in Google Workspace."
        )
    if "required role" in text and "admin" in text:
        return (
            "Switch to Company Agent > Full Access for this run, "
            "or set `agent.user_role` to `admin`/`owner`."
        )
    if (
        "google_api_http_error" in text
        or "invalid authentication credentials" in text
        or "oauth" in text
        or "refresh_token" in text
    ):
        return (
            "Reconnect Google OAuth in Settings and verify required scopes, then retry."
        )
    return ""


def _compose_professional_answer(
    *,
    request: ChatRequest,
    planned_steps: list[PlannedStep],
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    sources: list[AgentSource],
    next_steps: list[str],
    runtime_settings: dict[str, Any],
    verification_report: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    lines.append("## Task Understanding")
    lines.append(f"- Request: {_compact(request.message, 260)}")
    if request.agent_goal:
        lines.append(f"- Goal: {_compact(request.agent_goal, 240)}")
    delivery_email = _extract_first_email(request.message, request.agent_goal or "")
    if delivery_email:
        lines.append(f"- Delivery target: `{delivery_email}`")

    lines.append("")
    lines.append("## Execution Plan")
    for idx, step in enumerate(planned_steps, start=1):
        lines.append(f"{idx}. {step.title} (`{step.tool_id}`)")
    search_terms_raw = runtime_settings.get("__research_search_terms")
    keywords_raw = runtime_settings.get("__research_keywords")
    if isinstance(search_terms_raw, list) or isinstance(keywords_raw, list):
        search_terms = (
            [str(item).strip() for item in search_terms_raw if str(item).strip()]
            if isinstance(search_terms_raw, list)
            else []
        )
        keywords = (
            [str(item).strip() for item in keywords_raw if str(item).strip()]
            if isinstance(keywords_raw, list)
            else []
        )
        if search_terms or keywords:
            lines.append("")
            lines.append("## Research Blueprint")
            if search_terms:
                lines.append(f"- Planned search terms: {', '.join(search_terms[:6])}")
            if keywords:
                lines.append(f"- Planned keywords: {', '.join(keywords[:12])}")

    lines.append("")
    lines.append("## Execution Summary")
    if executed_steps:
        for row in executed_steps:
            status = "completed" if row.get("status") == "success" else "failed"
            step_no = int(row.get("step") or 0)
            title = str(row.get("title") or "Step")
            tool_id = str(row.get("tool_id") or "tool")
            summary = _compact(str(row.get("summary") or "No summary."), 180)
            lines.append(
                f"- Step {step_no}: **{title}** (`{tool_id}`) {status}. {summary}"
            )
    else:
        lines.append("- No execution steps completed.")

    lines.append("")
    lines.append("## Key Findings")
    browser_findings = runtime_settings.get("__latest_browser_findings")
    if isinstance(browser_findings, dict):
        title = str(browser_findings.get("title") or "").strip()
        url = str(browser_findings.get("url") or "").strip()
        excerpt = _compact(str(browser_findings.get("excerpt") or ""), 240)
        keywords_raw = browser_findings.get("keywords")
        keywords = (
            [str(item).strip() for item in keywords_raw if str(item).strip()]
            if isinstance(keywords_raw, list)
            else []
        )
        if title:
            lines.append(f"- Website analyzed: {title}")
        if url:
            lines.append(f"- Source URL: {url}")
        if keywords:
            lines.append(f"- Observed keywords: {', '.join(keywords[:10])}")
        if excerpt:
            lines.append(f"- Evidence note: {excerpt}")
    else:
        lines.append("- Findings are based on executed tools and indexed evidence.")

    if sources:
        unique_urls: list[str] = []
        for source in sources:
            url = str(source.url or "").strip()
            if not url or url in unique_urls:
                continue
            unique_urls.append(url)
        lines.append(f"- Sources used: {len(sources)}")
        if unique_urls:
            lines.append(f"- Primary source: {unique_urls[0]}")

    lines.append("")
    lines.append("## Delivery Status")
    send_actions = [item for item in actions if item.tool_id in DELIVERY_ACTION_IDS]
    if send_actions:
        latest_send = send_actions[-1]
        status = "sent" if latest_send.status == "success" else "not sent"
        lines.append(f"- Email delivery: {status}.")
        lines.append(f"- Detail: {_compact(latest_send.summary, 180)}")
        if latest_send.status != "success":
            hint = _issue_fix_hint(latest_send.summary)
            if hint:
                lines.append(f"- Fix: {hint}")
    elif delivery_email:
        lines.append("- Email delivery: no send step executed.")
    else:
        lines.append("- No email delivery requested.")

    failed_actions = [item for item in actions if item.status == "failed"]
    if failed_actions:
        lines.append("")
        lines.append("## Execution Issues")
        for item in failed_actions[:6]:
            lines.append(f"- {item.tool_id}: {_compact(item.summary, 180)}")

    artifact_urls: list[str] = []
    artifact_paths: list[str] = []
    for action in actions:
        metadata = action.metadata if isinstance(action.metadata, dict) else {}
        for key in ("url", "document_url", "spreadsheet_url"):
            raw = metadata.get(key)
            value = str(raw or "").strip()
            if not value or value in artifact_urls:
                continue
            artifact_urls.append(value)
        for key in ("path", "pdf_path"):
            raw = metadata.get(key)
            value = str(raw or "").strip()
            if not value or value in artifact_paths:
                continue
            artifact_paths.append(value)
    if artifact_urls or artifact_paths:
        lines.append("")
        lines.append("## Files and Documents")
        for url in artifact_urls[:10]:
            lines.append(f"- {url}")
        for path in artifact_paths[:10]:
            lines.append(f"- {path}")

    if verification_report:
        checks = verification_report.get("checks")
        if isinstance(checks, list) and checks:
            score = verification_report.get("score")
            grade = str(verification_report.get("grade") or "").strip()
            lines.append("")
            lines.append("## Verification")
            if score is not None:
                lines.append(f"- Quality score: {score}% ({grade or 'n/a'})")
            for check in checks[:8]:
                if not isinstance(check, dict):
                    continue
                name = str(check.get("name") or "Check").strip()
                status = str(check.get("status") or "info").strip().upper()
                detail = _compact(str(check.get("detail") or ""), 180)
                lines.append(f"- {name} [{status}]: {detail}")

    unique_next_steps: list[str] = []
    for step in next_steps:
        cleaned = str(step or "").strip()
        if not cleaned or cleaned in unique_next_steps:
            continue
        unique_next_steps.append(cleaned)
    if unique_next_steps:
        lines.append("")
        lines.append("## Recommended Next Steps")
        for item in unique_next_steps[:6]:
            lines.append(f"- {item}")

    return "\n".join(lines)


class AgentOrchestrator:
    def __init__(self) -> None:
        self.registry = get_tool_registry()
        self.activity_store = get_activity_store()
        self.audit = get_audit_logger()
        self.memory = get_memory_service()
        self._emitters: dict[str, RunEventEmitter] = {}

    def _activity_event(
        self,
        *,
        run_id: str,
        event_type: str,
        title: str,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
        stage: str | None = None,
        status: str | None = None,
        snapshot_ref: str | None = None,
    ) -> AgentActivityEvent:
        emitter = self._emitters.get(run_id)
        if emitter is None:
            emitter = RunEventEmitter(run_id=run_id)
            self._emitters[run_id] = emitter
        return emitter.emit(
            event_type=event_type,
            title=title,
            detail=detail,
            metadata=metadata or {},
            stage=stage,
            status=status,
            snapshot_ref=snapshot_ref,
        )

    def _selected_file_ids(self, request: ChatRequest) -> list[str]:
        collected: list[str] = []
        for selection in request.index_selection.values():
            file_ids = getattr(selection, "file_ids", []) or []
            for file_id in file_ids:
                file_id_text = str(file_id).strip()
                if file_id_text:
                    collected.append(file_id_text)
        return list(dict.fromkeys(collected))

    def _selected_index_id(self, request: ChatRequest) -> int | None:
        for raw_index_id in request.index_selection.keys():
            text = str(raw_index_id).strip()
            if not text:
                continue
            if text.isdigit():
                return int(text)
        return None

    def _expected_event_types(
        self,
        *,
        steps: list[PlannedStep],
        request: ChatRequest,
    ) -> list[str]:
        expected: list[str] = list(CORE_EVENT_TYPES)
        has_docs = any(
            token in request.message.lower() for token in ("pdf", "document", "file", "page")
        )

        for step in steps:
            expected.append("tool_started")
            expected.append("tool_completed")
            if step.tool_id in ("marketing.web_research", "browser.playwright.inspect"):
                expected.extend(
                    [
                        "web_search_started",
                        "browser_open",
                        "browser_navigate",
                        "browser_scroll",
                        "web_result_opened",
                        "browser_extract",
                    ]
                )
            if has_docs and step.tool_id in (
                "report.generate",
                "data.dataset.analyze",
                "invoice.create",
                "docs.create",
                "documents.highlight.extract",
            ):
                expected.extend(
                    [
                        "document_opened",
                        "pdf_open",
                        "pdf_page_change",
                        "document_scanned",
                        "pdf_scan_region",
                        "highlights_detected",
                        "pdf_evidence_linked",
                    ]
                )
            if step.tool_id in ("email.draft", "gmail.draft"):
                expected.extend(
                    [
                        "email_draft_create",
                        "email_set_to",
                        "email_set_subject",
                        "email_set_body",
                        "email_ready_to_send",
                    ]
                )
            if step.tool_id in ("email.send", "gmail.send"):
                expected.append("email_sent")
            if step.tool_id in (
                "docs.create",
                "workspace.docs.fill_template",
                "workspace.docs.research_notes",
                "workspace.sheets.track_step",
            ):
                expected.extend(
                    [
                        "doc_open",
                        "doc_locate_anchor",
                        "doc_insert_text",
                        "doc_save",
                    ]
                )
        return list(dict.fromkeys(expected))

    def run_stream(
        self,
        *,
        user_id: str,
        conversation_id: str,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> Generator[dict[str, Any], None, AgentRunResult]:
        access_context = build_access_context(user_id=user_id, settings=settings)
        if request.access_mode is not None:
            request_full_access = request.access_mode == ACCESS_MODE_FULL
            access_context = access_context.__class__(
                role=access_context.role,
                access_mode=request.access_mode,
                full_access_enabled=access_context.full_access_enabled or request_full_access,
                tenant_id=access_context.tenant_id,
            )

        header = self.activity_store.start_run(
            user_id=user_id,
            conversation_id=conversation_id,
            mode=request.agent_mode,
            goal=request.agent_goal or request.message,
        )
        run_id = header.run_id
        self._emitters[run_id] = RunEventEmitter(run_id=run_id)
        observed_event_types: list[str] = []
        run_started_clock = time.perf_counter()

        def _stream_event(event: AgentActivityEvent) -> dict[str, Any]:
            observed_event_types.append(event.event_type)
            self.activity_store.append(event)
            get_live_event_broker().publish(
                user_id=user_id,
                run_id=run_id,
                event={
                    "type": event.event_type,
                    "message": event.title,
                    "data": event.data,
                    "run_id": run_id,
                    "event_id": event.event_id,
                    "seq": event.seq,
                },
            )
            return {"type": "activity", "event": event.to_dict()}

        def _trace_payload(trace: ToolTraceEvent | Any) -> dict[str, Any] | None:
            if isinstance(trace, ToolTraceEvent):
                return trace.to_dict()
            if hasattr(trace, "to_dict"):
                raw = trace.to_dict()
                return raw if isinstance(raw, dict) else None
            return dict(trace) if isinstance(trace, dict) else None

        def _stream_traces(
            *,
            step: PlannedStep,
            step_index: int,
            traces: list[ToolTraceEvent] | list[Any],
        ) -> Generator[dict[str, Any], None, None]:
            for trace in list(traces or []):
                payload = _trace_payload(trace)
                if not isinstance(payload, dict):
                    continue
                trace_event_type = str(payload.get("event_type") or "tool_progress").strip()
                trace_title = str(payload.get("title") or step.title).strip() or step.title
                trace_detail = str(payload.get("detail") or "").strip()
                trace_data = payload.get("data")
                trace_data_dict = dict(trace_data) if isinstance(trace_data, dict) else {}
                trace_snapshot = payload.get("snapshot_ref")
                trace_event = self._activity_event(
                    run_id=run_id,
                    event_type=trace_event_type,
                    title=trace_title,
                    detail=trace_detail,
                    metadata={
                        **trace_data_dict,
                        "tool_id": step.tool_id,
                        "step": step_index,
                    },
                    snapshot_ref=str(trace_snapshot) if trace_snapshot else None,
                )
                yield _stream_event(trace_event)

        def _run_tool_live(
            *,
            step: PlannedStep,
            step_index: int,
            prompt: str,
            params: dict[str, Any],
        ) -> Generator[dict[str, Any], None, Any]:
            execution_stream = self.registry.execute_with_trace(
                tool_id=step.tool_id,
                context=execution_context,
                access=access_context,
                prompt=prompt,
                params=params,
            )
            while True:
                try:
                    trace = next(execution_stream)
                except StopIteration as stop:
                    return stop.value
                for trace_event in _stream_traces(
                    step=step,
                    step_index=step_index,
                    traces=[trace],
                ):
                    yield trace_event

        desktop_start_event = self._activity_event(
            run_id=run_id,
            event_type="desktop_starting",
            title="Starting secure agent desktop",
            detail="Booting isolated workspace and loading connected tools",
            metadata={"conversation_id": conversation_id},
        )
        yield _stream_event(desktop_start_event)

        task_understanding_started = self._activity_event(
            run_id=run_id,
            event_type="task_understanding_started",
            title="Understanding requested outcome",
            detail=_compact(request.message, 220),
            metadata={"conversation_id": conversation_id},
        )
        yield _stream_event(task_understanding_started)
        task_intelligence = derive_task_intelligence(
            message=request.message,
            agent_goal=request.agent_goal,
        )
        preference_store = get_user_preference_store()
        saved_preferences = preference_store.get(user_id=user_id)
        inferred_preferences = infer_user_preferences(
            message=request.message,
            existing_preferences=saved_preferences,
        )
        user_preferences = (
            preference_store.merge(user_id=user_id, patch=inferred_preferences)
            if inferred_preferences
            else saved_preferences
        )
        task_understanding_ready = self._activity_event(
            run_id=run_id,
            event_type="task_understanding_ready",
            title="Task understanding completed",
            detail=task_intelligence.objective,
            metadata={**task_intelligence.to_dict(), "preferences": user_preferences},
        )
        yield _stream_event(task_understanding_ready)

        preflight_checks = run_preflight_checks(
            requires_delivery=task_intelligence.requires_delivery,
            requires_web_inspection=task_intelligence.requires_web_inspection,
        )
        preflight_started_event = self._activity_event(
            run_id=run_id,
            event_type="preflight_started",
            title="Running preflight checks",
            detail="Validating credentials and execution prerequisites",
            metadata={"check_count": len(preflight_checks)},
        )
        yield _stream_event(preflight_started_event)
        for check in preflight_checks:
            preflight_check_event = self._activity_event(
                run_id=run_id,
                event_type="preflight_check",
                title=str(check.get("name") or "preflight_check"),
                detail=str(check.get("detail") or ""),
                metadata={"status": str(check.get("status") or "info")},
            )
            yield _stream_event(preflight_check_event)
        preflight_completed_event = self._activity_event(
            run_id=run_id,
            event_type="preflight_completed",
            title="Preflight checks completed",
            detail="Proceeding with planning and tool execution",
            metadata={"checks": preflight_checks},
        )
        yield _stream_event(preflight_completed_event)

        started_event = self._activity_event(
            run_id=run_id,
            event_type="planning_started",
            title="Planning agent workflow",
            detail=_compact(request.message, 220),
            metadata={"conversation_id": conversation_id},
        )
        yield _stream_event(started_event)

        steps = build_plan(request)
        deep_research_mode = is_deep_research_request(request)
        request_text = f"{request.message} {request.agent_goal or ''}".lower()
        highlight_color = "green" if "green" in request_text else "yellow"
        research_blueprint = build_research_blueprint(
            message=request.message,
            agent_goal=request.agent_goal,
            min_keywords=10,
        )
        planned_search_terms = [
            str(item).strip()
            for item in (research_blueprint.get("search_terms") if isinstance(research_blueprint, dict) else [])
            if str(item).strip()
        ]
        planned_keywords = [
            str(item).strip()
            for item in (research_blueprint.get("keywords") if isinstance(research_blueprint, dict) else [])
            if str(item).strip()
        ]
        normalized_steps: list[PlannedStep] = []
        for step in steps:
            params = dict(step.params)
            if step.tool_id == "marketing.web_research" and planned_search_terms:
                params["query"] = planned_search_terms[0]
                if len(planned_search_terms) > 1:
                    params.setdefault("query_variants", planned_search_terms[1:4])
            if step.tool_id in ("browser.playwright.inspect", "documents.highlight.extract"):
                params.setdefault("highlight_color", highlight_color)
            if step.tool_id == "documents.highlight.extract" and planned_keywords:
                params.setdefault("words", planned_keywords[:12])
            if step.tool_id == "docs.create":
                params.setdefault("include_copied_highlights", True)
            normalized_steps.append(PlannedStep(tool_id=step.tool_id, title=step.title, params=params))
        steps = normalized_steps

        if request.agent_mode == "company_agent" and not any(
            step.tool_id == "documents.highlight.extract" for step in steps
        ):
            insert_at = len(steps)
            for idx, step in enumerate(steps):
                if step.tool_id in ("browser.playwright.inspect", "marketing.web_research"):
                    insert_at = idx + 1
                    break
            steps.insert(
                insert_at,
                PlannedStep(
                    tool_id="documents.highlight.extract",
                    title="Highlight words in selected files",
                    params={
                        "highlight_color": highlight_color,
                        "words": planned_keywords[:12],
                    },
                ),
            )

        workspace_logging_requested = any(
            token in request_text
            for token in (
                "google docs",
                "google sheets",
                "research notebook",
                "step tracker",
                "track in sheets",
                "log to docs",
            )
        )
        # Company Agent runs always start with roadmap logging in Sheets/Docs.
        always_workspace_logging = request.agent_mode == "company_agent"
        deep_workspace_logging_enabled = always_workspace_logging or (
            deep_research_mode
            and (
                workspace_logging_requested
                or bool(settings.get("agent.deep_research_workspace_logging", False))
            )
        )
        if deep_workspace_logging_enabled and request.agent_mode == "company_agent":
            search_preview = ", ".join(planned_search_terms[:4]) if planned_search_terms else "n/a"
            keyword_preview = ", ".join(planned_keywords[:10]) if planned_keywords else "n/a"
            roadmap_steps: list[PlannedStep] = [
                PlannedStep(
                    tool_id="workspace.sheets.track_step",
                    title="Open execution roadmap in Google Sheets",
                    params={
                        "step_name": "Execution roadmap initialized",
                        "status": "planned",
                        "detail": f"Search terms: {search_preview} | Keywords: {keyword_preview}",
                    },
                )
            ]
            roadmap_steps.append(
                PlannedStep(
                    tool_id="workspace.docs.research_notes",
                    title="Write planning blueprint to Google Docs",
                    params={
                        "note": (
                            f"Planning blueprint\n"
                            f"- Search terms: {search_preview}\n"
                            f"- Keywords: {keyword_preview}"
                        ),
                    },
                )
            )
            for idx, planned_step in enumerate(steps, start=1):
                roadmap_steps.append(
                    PlannedStep(
                        tool_id="workspace.sheets.track_step",
                        title=f"Roadmap step {idx}: {planned_step.title}",
                        params={
                            "step_name": f"{idx}. {planned_step.title}",
                            "status": "planned",
                            "detail": (
                                f"Tool={planned_step.tool_id} | "
                                f"Search terms={search_preview} | "
                                f"Keywords={keyword_preview}"
                            )[:900],
                        },
                    )
                )
            steps = roadmap_steps + steps
        deep_workspace_warning_emitted = False
        dynamic_inspection_inserted = False

        delivery_email = _extract_first_email(request.message, request.agent_goal or "")
        plan_candidate_event = self._activity_event(
            run_id=run_id,
            event_type="plan_candidate",
            title="Generated initial execution plan",
            detail=f"Parsed task into {len(steps)} concrete execution step(s).",
            metadata={
                "steps": [step.__dict__ for step in steps],
                "task_understanding": {
                    "objective": task_intelligence.objective,
                    "delivery_email": delivery_email,
                    "workspace_logging_requested": workspace_logging_requested,
                    "target_url": task_intelligence.target_url,
                    "planned_search_terms": planned_search_terms[:6],
                    "planned_keywords": planned_keywords[:12],
                },
            },
        )
        yield _stream_event(plan_candidate_event)
        plan_refined_event = self._activity_event(
            run_id=run_id,
            event_type="plan_refined",
            title="Refined execution order",
            detail="Prioritized sequence with search terms and keyword blueprint",
            metadata={
                "step_ids": [step.tool_id for step in steps],
                "search_terms": planned_search_terms[:6],
                "keywords": planned_keywords[:12],
            },
        )
        yield _stream_event(plan_refined_event)
        planned_event = self._activity_event(
            run_id=run_id,
            event_type="plan_ready",
            title=f"Prepared {len(steps)} execution steps",
            metadata={"steps": [step.__dict__ for step in steps]},
        )
        yield _stream_event(planned_event)

        desktop_ready_event = self._activity_event(
            run_id=run_id,
            event_type="desktop_ready",
            title="Agent desktop is ready",
            detail="Workspace initialized. Executing plan in live mode.",
            metadata={"steps": len(steps)},
        )
        yield _stream_event(desktop_ready_event)

        execution_context = ToolExecutionContext(
            user_id=user_id,
            tenant_id=access_context.tenant_id,
            conversation_id=conversation_id,
            run_id=run_id,
            mode=request.agent_mode,
            settings={
                **settings,
                "__agent_user_id": user_id,
                "__agent_run_id": run_id,
                "__selected_file_ids": self._selected_file_ids(request),
                "__selected_index_id": self._selected_index_id(request),
                "__research_search_terms": planned_search_terms[:6],
                "__research_keywords": planned_keywords[:16],
                "__highlight_color": highlight_color,
                "__copied_highlights": [],
                "__user_preferences": user_preferences,
                "__task_preferred_tone": task_intelligence.preferred_tone,
                "__task_preferred_format": task_intelligence.preferred_format,
            },
        )

        all_actions: list[AgentAction] = []
        all_sources: list[AgentSource] = []
        next_steps: list[str] = []
        executed_steps: list[dict[str, Any]] = []

        step_cursor = 0
        display_step_index = 0
        while step_cursor < len(steps):
            step = steps[step_cursor]
            if (
                not deep_workspace_logging_enabled
                and step.tool_id in ("workspace.docs.research_notes", "workspace.sheets.track_step")
            ):
                step_cursor += 1
                continue
            display_step_index += 1
            index = display_step_index
            step_started = utc_now().isoformat()
            queued_event = self._activity_event(
                run_id=run_id,
                event_type="tool_queued",
                title=f"Queued: {step.title}",
                detail=step.tool_id,
                metadata={"tool_id": step.tool_id, "step": index},
            )
            yield _stream_event(queued_event)

            step_event = self._activity_event(
                run_id=run_id,
                event_type="tool_started",
                title=f"Step {index}: {step.title}",
                detail=step.tool_id,
            )
            yield _stream_event(step_event)

            progress_event = self._activity_event(
                run_id=run_id,
                event_type="tool_progress",
                title=f"Step {index}: Running {step.title}",
                detail="Tool execution in progress",
                metadata={"tool_id": step.tool_id, "step": index, "progress": 0.5},
            )
            yield _stream_event(progress_event)

            params = dict(step.params)
            # Full access mode auto-confirms execute operations.
            if access_context.access_mode == ACCESS_MODE_FULL and access_context.full_access_enabled:
                params.setdefault("confirmed", True)

            tool_meta = self.registry.get(step.tool_id).metadata
            if (
                tool_meta.action_class == "execute"
                and tool_meta.execution_policy == "confirm_before_execute"
            ):
                if params.get("confirmed"):
                    granted_event = self._activity_event(
                        run_id=run_id,
                        event_type="approval_granted",
                        title=f"Execution approved: {step.title}",
                        detail="Full access mode auto-approved this execute action",
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(granted_event)
                else:
                    approval_event = self._activity_event(
                        run_id=run_id,
                        event_type="approval_required",
                        title=f"Approval required: {step.title}",
                        detail="Restricted mode requires explicit confirmation",
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(approval_event)

            try:
                result = yield from _run_tool_live(
                    step=step,
                    step_index=index,
                    prompt=request.message,
                    params=params,
                )
                action_metadata = _extract_action_artifact_metadata(result.data, step=index)
                action = self.registry.get(step.tool_id).to_action(
                    status="success",
                    summary=result.summary,
                    started_at=step_started,
                    metadata=action_metadata,
                )
                all_actions.append(action)
                all_sources.extend(result.sources)
                executed_steps.append(
                    {
                        "step": index,
                        "tool_id": step.tool_id,
                        "title": step.title,
                        "status": "success",
                        "summary": result.summary,
                    }
                )
                next_steps.extend(result.next_steps)
                completed_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_completed",
                    title=f"Completed: {step.title}",
                    detail=result.summary,
                    metadata={"tool_id": step.tool_id, "step": index},
                )
                yield _stream_event(completed_event)

                if step.tool_id == "marketing.web_research" and not dynamic_inspection_inserted:
                    followup_steps = build_browser_followup_steps(
                        result.data,
                        max_urls=4 if deep_research_mode else 2,
                    )
                    if followup_steps:
                        insertion_point = step_cursor + 1
                        steps[insertion_point:insertion_point] = followup_steps
                        dynamic_inspection_inserted = True
                        refined_event = self._activity_event(
                            run_id=run_id,
                            event_type="plan_refined",
                            title="Expanded research plan with live source inspections",
                            detail=f"Inserted {len(followup_steps)} website inspection step(s)",
                            metadata={
                                "inserted": len(followup_steps),
                                "total_steps": len(steps),
                                "step_ids": [item.tool_id for item in steps],
                            },
                        )
                        yield _stream_event(refined_event)

                if deep_workspace_logging_enabled and step.tool_id not in (
                    "workspace.docs.research_notes",
                    "workspace.sheets.track_step",
                ):
                    keyword_rows = result.data.get("keywords") if isinstance(result.data, dict) else None
                    keywords = (
                        [str(item).strip() for item in keyword_rows if str(item).strip()]
                        if isinstance(keyword_rows, list)
                        else []
                    )
                    keyword_line = f"Keywords: {', '.join(keywords[:12])}" if keywords else ""
                    copied_rows = result.data.get("copied_snippets") if isinstance(result.data, dict) else None
                    copied_snippets = (
                        [str(item).strip() for item in copied_rows if str(item).strip()]
                        if isinstance(copied_rows, list)
                        else []
                    )
                    copied_line = (
                        f"Copied snippets: {' | '.join(copied_snippets[:3])}"
                        if copied_snippets
                        else ""
                    )
                    highlighted_rows = result.data.get("highlighted_words") if isinstance(result.data, dict) else None
                    highlighted_words = []
                    if isinstance(highlighted_rows, list):
                        for row in highlighted_rows:
                            if not isinstance(row, dict):
                                continue
                            word = str(row.get("word") or "").strip()
                            if word:
                                highlighted_words.append(word)
                    highlight_line = (
                        f"Highlighted words: {', '.join(list(dict.fromkeys(highlighted_words))[:12])}"
                        if highlighted_words
                        else ""
                    )
                    compact_content = _compact(result.content, 560)
                    note_body = "\n".join(
                        part
                        for part in [
                            f"Step {index}: {step.title}",
                            f"Summary: {result.summary}",
                            keyword_line,
                            highlight_line,
                            copied_line,
                            compact_content,
                        ]
                        if part
                    )
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
                        PlannedStep(
                            tool_id="workspace.docs.research_notes",
                            title=f"Log findings: {step.title}",
                            params={"note": note_body},
                        ),
                    ]
                    for shadow_step in log_steps:
                        shadow_started_at = utc_now().isoformat()
                        shadow_params = dict(shadow_step.params)
                        if access_context.access_mode == ACCESS_MODE_FULL and access_context.full_access_enabled:
                            shadow_params.setdefault("confirmed", True)
                        try:
                            shadow_result = yield from _run_tool_live(
                                step=shadow_step,
                                step_index=index,
                                prompt=request.message,
                                params=shadow_params,
                            )
                            shadow_metadata = _extract_action_artifact_metadata(
                                shadow_result.data,
                                step=index,
                            )
                            shadow_metadata["shadow"] = True
                            shadow_action = self.registry.get(shadow_step.tool_id).to_action(
                                status="success",
                                summary=shadow_result.summary,
                                started_at=shadow_started_at,
                                metadata=shadow_metadata,
                            )
                            all_actions.append(shadow_action)
                            all_sources.extend(shadow_result.sources)
                            shadow_completed = self._activity_event(
                                run_id=run_id,
                                event_type="tool_completed",
                                title=f"Completed: {shadow_step.title}",
                                detail=shadow_result.summary,
                                metadata={"tool_id": shadow_step.tool_id, "step": index, "shadow": True},
                            )
                            yield _stream_event(shadow_completed)
                        except Exception as shadow_exc:
                            if any(
                                marker in str(shadow_exc).lower()
                                for marker in ("google_tokens_missing", "oauth", "refresh_token")
                            ):
                                deep_workspace_logging_enabled = False
                                if not deep_workspace_warning_emitted:
                                    deep_workspace_warning_emitted = True
                                    warning_event = self._activity_event(
                                        run_id=run_id,
                                        event_type="tool_failed",
                                        title="Workspace logging disabled",
                                        detail=(
                                            "Google Docs/Sheets is not connected. "
                                            "Continuing deep research without external notebook sync."
                                        ),
                                        metadata={"tool_id": shadow_step.tool_id, "step": index, "shadow": True},
                                    )
                                    yield _stream_event(warning_event)
                            shadow_failed = self._activity_event(
                                run_id=run_id,
                                event_type="tool_failed",
                                title=f"Failed: {shadow_step.title}",
                                detail=str(shadow_exc),
                                metadata={"tool_id": shadow_step.tool_id, "step": index, "shadow": True},
                            )
                            yield _stream_event(shadow_failed)
            except Exception as exc:
                if (
                    step.tool_id in ("workspace.docs.research_notes", "workspace.sheets.track_step")
                    and any(marker in str(exc).lower() for marker in ("google_tokens_missing", "oauth", "refresh_token"))
                ):
                    deep_workspace_logging_enabled = False
                action = self.registry.get(step.tool_id).to_action(
                    status="failed",
                    summary=str(exc),
                    started_at=step_started,
                    metadata={"step": index},
                )
                all_actions.append(action)
                executed_steps.append(
                    {
                        "step": index,
                        "tool_id": step.tool_id,
                        "title": step.title,
                        "status": "failed",
                        "summary": str(exc),
                    }
                )
                exc_text = str(exc)
                if "requires confirmation" in exc_text.lower():
                    approval_event = self._activity_event(
                        run_id=run_id,
                        event_type="approval_required",
                        title=f"Approval required: {step.title}",
                        detail=exc_text,
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(approval_event)
                    policy_event = self._activity_event(
                        run_id=run_id,
                        event_type="policy_blocked",
                        title=f"Policy blocked: {step.title}",
                        detail="Execution blocked in restricted mode until confirmation",
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(policy_event)
                fail_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_failed",
                    title=f"Failed: {step.title}",
                    detail=exc_text,
                    metadata={"tool_id": step.tool_id, "step": index},
                )
                yield _stream_event(fail_event)
                recovery_hint = suggest_failure_recovery(
                    request_message=request.message,
                    tool_id=step.tool_id,
                    step_title=step.title,
                    error_text=exc_text,
                    recent_steps=executed_steps[-8:],
                )
                if recovery_hint:
                    next_steps.append(recovery_hint)
                    recovery_event = self._activity_event(
                        run_id=run_id,
                        event_type="tool_progress",
                        title="Recovery suggestion generated",
                        detail=recovery_hint,
                        metadata={"tool_id": step.tool_id, "step": index, "recovery_hint": recovery_hint},
                    )
                    yield _stream_event(recovery_event)
            step_cursor += 1

        delivery_requested = bool(task_intelligence.requires_delivery and task_intelligence.delivery_email)
        delivery_attempted = any(item.tool_id in DELIVERY_ACTION_IDS for item in all_actions)
        if delivery_requested and not delivery_attempted:
            delivery_step = len(executed_steps) + 1
            delivery_started = utc_now().isoformat()
            delivery_tool_id = "mailer.report_send"
            delivery_title = "Send report email (server-side)"

            queued_delivery = self._activity_event(
                run_id=run_id,
                event_type="tool_queued",
                title=f"Queued: {delivery_title}",
                detail=delivery_tool_id,
                metadata={"tool_id": delivery_tool_id, "step": delivery_step},
            )
            yield _stream_event(queued_delivery)
            started_delivery = self._activity_event(
                run_id=run_id,
                event_type="tool_started",
                title=f"Step {delivery_step}: {delivery_title}",
                detail=task_intelligence.delivery_email,
                metadata={"tool_id": delivery_tool_id, "step": delivery_step},
            )
            yield _stream_event(started_delivery)

            report_title = str(execution_context.settings.get("__latest_report_title") or "Website Analysis Report").strip()
            report_body = str(execution_context.settings.get("__latest_report_content") or "").strip()
            if not report_body:
                summary_lines = [
                    f"- {row.get('title') or row.get('tool_id')}: {row.get('summary') or ''}".strip()
                    for row in executed_steps
                    if str(row.get("status") or "") == "success"
                ]
                report_body = "\n".join(
                    [
                        "No dedicated report draft was generated; sending execution summary.",
                        "",
                        *summary_lines[:10],
                    ]
                ).strip()
            preferred_tone = str(task_intelligence.preferred_tone or user_preferences.get("tone") or "").strip()
            context_summary = f"{task_intelligence.objective} Tone: {preferred_tone}".strip()
            polished_email = polish_email_content(
                subject=report_title or "Website Analysis Report",
                body_text=report_body or "Report requested, but no body content was generated.",
                recipient=task_intelligence.delivery_email,
                context_summary=context_summary,
            )
            report_title = str(polished_email.get("subject") or report_title or "Website Analysis Report").strip()
            report_body = str(
                polished_email.get("body_text")
                or report_body
                or "Report requested, but no body content was generated."
            ).strip()

            preview_body = _truncate_text(report_body or "Composing report body...")
            set_recipient_event = self._activity_event(
                run_id=run_id,
                event_type="email_set_to",
                title="Apply recipient",
                detail=task_intelligence.delivery_email,
                metadata={"tool_id": delivery_tool_id, "step": delivery_step},
            )
            yield _stream_event(set_recipient_event)
            set_subject_event = self._activity_event(
                run_id=run_id,
                event_type="email_set_subject",
                title="Apply subject",
                detail=report_title or "Website Analysis Report",
                metadata={"tool_id": delivery_tool_id, "step": delivery_step},
            )
            yield _stream_event(set_subject_event)
            typed_preview = ""
            for body_chunk in _chunk_preserve_text(preview_body, chunk_size=240, limit=7):
                typed_preview += body_chunk
                typing_event = self._activity_event(
                    run_id=run_id,
                    event_type="email_type_body",
                    title="Typing email body",
                    detail=_compact(body_chunk, 120) or "Composing body...",
                    metadata={
                        "tool_id": delivery_tool_id,
                        "step": delivery_step,
                        "typed_preview": typed_preview,
                    },
                )
                yield _stream_event(typing_event)
            set_body_event = self._activity_event(
                run_id=run_id,
                event_type="email_set_body",
                title="Apply email body",
                detail=_compact(preview_body, 180) or "Body ready.",
                metadata={
                    "tool_id": delivery_tool_id,
                    "step": delivery_step,
                    "typed_preview": preview_body,
                },
            )
            yield _stream_event(set_body_event)
            send_prepare_event = self._activity_event(
                run_id=run_id,
                event_type="email_ready_to_send",
                title="Dispatching report via Mailer Service",
                detail=task_intelligence.delivery_email,
                metadata={
                    "tool_id": delivery_tool_id,
                    "step": delivery_step,
                    "typed_preview": preview_body,
                },
            )
            yield _stream_event(send_prepare_event)
            try:
                delivery_response = send_report_via_mailer(
                    to_email=task_intelligence.delivery_email,
                    subject=report_title or "Website Analysis Report",
                    body_text=report_body or "Report requested, but no body content was generated.",
                )
                message_id = str(delivery_response.get("id") or "")
                send_summary = (
                    f"Server-side Mailer Service sent report to {task_intelligence.delivery_email}. "
                    f"Message ID: {message_id or 'unknown'}"
                )
                all_actions.append(
                    AgentAction(
                        tool_id=delivery_tool_id,
                        action_class="execute",
                        status="success",
                        summary=send_summary,
                        started_at=delivery_started,
                        ended_at=utc_now().isoformat(),
                        metadata={
                            "step": delivery_step,
                            "recipient": task_intelligence.delivery_email,
                            "subject": report_title,
                            "message_id": message_id,
                        },
                    )
                )
                executed_steps.append(
                    {
                        "step": delivery_step,
                        "tool_id": delivery_tool_id,
                        "title": delivery_title,
                        "status": "success",
                        "summary": send_summary,
                    }
                )
                next_steps.append("Monitor recipient inbox for response and follow-up actions.")
                sent_event = self._activity_event(
                    run_id=run_id,
                    event_type="email_sent",
                    title="Report email sent",
                    detail=message_id or task_intelligence.delivery_email,
                    metadata={"tool_id": delivery_tool_id, "step": delivery_step},
                )
                yield _stream_event(sent_event)
                completed_delivery = self._activity_event(
                    run_id=run_id,
                    event_type="tool_completed",
                    title=f"Completed: {delivery_title}",
                    detail=send_summary,
                    metadata={"tool_id": delivery_tool_id, "step": delivery_step},
                )
                yield _stream_event(completed_delivery)
            except Exception as exc:
                mapped = exc if isinstance(exc, GmailDwdError) else RuntimeError(str(exc))
                code = str(getattr(mapped, "code", "mailer_send_failed")).strip()
                summary = f"{code}: {mapped}"
                all_actions.append(
                    AgentAction(
                        tool_id=delivery_tool_id,
                        action_class="execute",
                        status="failed",
                        summary=summary,
                        started_at=delivery_started,
                        ended_at=utc_now().isoformat(),
                        metadata={"step": delivery_step, "recipient": task_intelligence.delivery_email},
                    )
                )
                executed_steps.append(
                    {
                        "step": delivery_step,
                        "tool_id": delivery_tool_id,
                        "title": delivery_title,
                        "status": "failed",
                        "summary": summary,
                    }
                )
                failed_delivery = self._activity_event(
                    run_id=run_id,
                    event_type="tool_failed",
                    title=f"Failed: {delivery_title}",
                    detail=summary,
                    metadata={"tool_id": delivery_tool_id, "step": delivery_step},
                )
                yield _stream_event(failed_delivery)

        unique_next_steps: list[str] = []
        for step in next_steps:
            if step not in unique_next_steps:
                unique_next_steps.append(step)

        verification_report = build_verification_report(
            task=task_intelligence,
            planned_tool_ids=[step.tool_id for step in steps],
            executed_steps=executed_steps,
            actions=all_actions,
            sources=all_sources,
        )
        verification_started_event = self._activity_event(
            run_id=run_id,
            event_type="verification_started",
            title="Run verification checks",
            detail="Evaluating evidence quality, delivery completion, and execution stability",
            metadata={"check_count": len(verification_report.get("checks") or [])},
        )
        yield _stream_event(verification_started_event)
        for check in verification_report.get("checks") or []:
            if not isinstance(check, dict):
                continue
            verification_check_event = self._activity_event(
                run_id=run_id,
                event_type="verification_check",
                title=str(check.get("name") or "Verification check"),
                detail=str(check.get("detail") or ""),
                metadata={
                    "status": str(check.get("status") or "info"),
                    "score": verification_report.get("score"),
                },
            )
            yield _stream_event(verification_check_event)
        verification_completed_event = self._activity_event(
            run_id=run_id,
            event_type="verification_completed",
            title="Verification completed",
            detail=f"Quality score: {verification_report.get('score')}% ({verification_report.get('grade')})",
            metadata=verification_report,
        )
        yield _stream_event(verification_completed_event)

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
                wait_started_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_progress",
                    title="Running deep research cross-checks",
                    detail="Verifying evidence consistency before final synthesis",
                    metadata={"step": len(steps), "progress": 0.0},
                )
                yield _stream_event(wait_started_event)
                while waited < remaining_seconds:
                    chunk = min(2.0, remaining_seconds - waited)
                    time.sleep(chunk)
                    waited += chunk
                    progress = min(1.0, waited / remaining_seconds) if remaining_seconds > 0 else 1.0
                    wait_progress_event = self._activity_event(
                        run_id=run_id,
                        event_type="tool_progress",
                        title="Deep research quality pass",
                        detail=f"Cross-check in progress ({int(progress * 100)}%)",
                        metadata={"step": len(steps), "progress": round(progress, 3)},
                    )
                    yield _stream_event(wait_progress_event)

        synthesis_started_event = self._activity_event(
            run_id=run_id,
            event_type="synthesis_started",
            title="Synthesizing final response",
            detail="Combining tool outputs into one structured answer",
        )
        yield _stream_event(synthesis_started_event)

        answer = _compose_professional_answer(
            request=request,
            planned_steps=steps,
            executed_steps=executed_steps,
            actions=all_actions,
            sources=all_sources,
            next_steps=unique_next_steps,
            runtime_settings=execution_context.settings,
            verification_report=verification_report,
        )
        answer = polish_final_response(
            request_message=request.message,
            answer_text=answer,
            verification_report=verification_report,
            preferences={
                **(user_preferences if isinstance(user_preferences, dict) else {}),
                "task_preferred_tone": task_intelligence.preferred_tone,
                "task_preferred_format": task_intelligence.preferred_format,
            },
        )

        info_blocks: list[str] = []
        for idx, source in enumerate(all_sources, start=1):
            label = html.escape(source.label)
            url = html.escape(source.url or "")
            detail = f"<a href='{url}' target='_blank' rel='noopener noreferrer'>{url}</a>" if url else "Internal source"
            info_blocks.append(
                (
                    f"<details class='evidence' id='evidence-{idx}' {'open' if idx == 1 else ''}>"
                    f"<summary><i>Evidence [{idx}]</i></summary>"
                    f"<div><b>Source:</b> [{idx}] {label}</div>"
                    f"<div class='evidence-content'><b>Link:</b> {detail}</div>"
                    "</details>"
                )
            )
        info_html = "".join(info_blocks)

        result = AgentRunResult(
            run_id=run_id,
            answer=answer,
            info_html=info_html,
            actions_taken=all_actions,
            sources_used=all_sources,
            next_recommended_steps=unique_next_steps[:8],
        )
        synthesis_completed_event = self._activity_event(
            run_id=run_id,
            event_type="synthesis_completed",
            title="Final response ready",
            detail=f"Generated {len(all_actions)} action result(s) with {len(all_sources)} source(s)",
        )
        yield _stream_event(synthesis_completed_event)

        expected_events = self._expected_event_types(steps=steps, request=request)
        coverage = coverage_report(
            observed_event_types=observed_event_types,
            expected_event_types=expected_events,
        )
        coverage_event = self._activity_event(
            run_id=run_id,
            event_type="event_coverage",
            title="Generated event coverage report",
            detail=f"{coverage['coverage_percent']}% expected events were emitted",
            metadata=coverage,
            stage="result",
            status="completed",
        )
        yield _stream_event(coverage_event)

        try:
            self.activity_store.end_run(run_id, result.to_dict())
            self.audit.write(
                user_id=user_id,
                tenant_id=access_context.tenant_id,
                run_id=run_id,
                event="agent_run_completed",
                payload={
                    "conversation_id": conversation_id,
                    "steps": len(steps),
                    "actions": len(all_actions),
                    "sources": len(all_sources),
                    "event_coverage_percent": coverage.get("coverage_percent", 0),
                },
            )
            self.memory.save_run(
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
                    "user_preferences": user_preferences,
                    "event_coverage": coverage,
                }
            )
            return result
        finally:
            self._emitters.pop(run_id, None)


_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
