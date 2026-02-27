from __future__ import annotations

import html
import json
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
    build_location_delivery_brief,
    curate_next_steps_for_task,
    polish_email_content,
    rewrite_task_for_execution,
    summarize_step_outcome,
    suggest_failure_recovery,
)
from api.services.agent.llm_contracts import (
    build_task_contract,
    propose_fact_probe_steps,
    verify_task_contract_fulfillment,
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
    LLM_ALLOWED_TOOL_IDS,
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
GUARDED_ACTION_TOOL_IDS = (
    "mailer.report_send",
    "email.send",
    "gmail.send",
    "browser.contact_form.send",
    "invoice.send",
    "slack.post_message",
)


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
    rewritten_task = " ".join(str(runtime_settings.get("__task_rewrite_detail") or "").split()).strip()
    if rewritten_task:
        lines.append(f"- Rewritten brief: {_compact(rewritten_task, 260)}")
    rewrite_deliverables = runtime_settings.get("__task_rewrite_deliverables")
    if isinstance(rewrite_deliverables, list):
        cleaned_deliverables = [str(item).strip() for item in rewrite_deliverables if str(item).strip()]
        if cleaned_deliverables:
            lines.append(f"- Deliverables: {', '.join(cleaned_deliverables[:6])}")
    rewrite_constraints = runtime_settings.get("__task_rewrite_constraints")
    if isinstance(rewrite_constraints, list):
        cleaned_constraints = [str(item).strip() for item in rewrite_constraints if str(item).strip()]
        if cleaned_constraints:
            lines.append(f"- Constraints: {', '.join(cleaned_constraints[:6])}")
    contract_missing = runtime_settings.get("__task_clarification_missing")
    if isinstance(contract_missing, list):
        cleaned_missing = [str(item).strip() for item in contract_missing if str(item).strip()]
        if cleaned_missing:
            lines.append(f"- Missing requirements: {', '.join(cleaned_missing[:6])}")
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
    clarification_questions = runtime_settings.get("__task_clarification_questions")
    if isinstance(clarification_questions, list):
        cleaned_questions = [str(item).strip() for item in clarification_questions if str(item).strip()]
        if cleaned_questions:
            lines.append("## Clarification Needed")
            for question in cleaned_questions[:6]:
                lines.append(f"- {question}")
            lines.append("")

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

    contract_check = runtime_settings.get("__task_contract_check")
    if isinstance(contract_check, dict):
        ready_final = bool(contract_check.get("ready_for_final_response"))
        ready_actions = bool(contract_check.get("ready_for_external_actions"))
        missing_items = (
            [str(item).strip() for item in contract_check.get("missing_items", []) if str(item).strip()]
            if isinstance(contract_check.get("missing_items"), list)
            else []
        )
        reason = " ".join(str(contract_check.get("reason") or "").split()).strip()
        lines.append("")
        lines.append("## Contract Gate")
        lines.append(f"- Final response ready: {'yes' if ready_final else 'no'}.")
        lines.append(f"- External actions ready: {'yes' if ready_actions else 'no'}.")
        if missing_items:
            lines.append(f"- Missing items: {', '.join(missing_items[:6])}")
        if reason:
            lines.append(f"- Reason: {_compact(reason, 180)}")

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
            if step.tool_id == "browser.contact_form.send":
                expected.extend(
                    [
                        "browser_open",
                        "browser_cookie_accept",
                        "browser_contact_form_detected",
                        "browser_contact_fill_name",
                        "browser_contact_fill_email",
                        "browser_contact_fill_subject",
                        "browser_contact_fill_message",
                        "browser_contact_submit",
                        "browser_contact_confirmation",
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
            if step.tool_id in ("workspace.docs.fill_template", "workspace.docs.research_notes"):
                expected.extend(
                    [
                        "docs.create_started",
                        "docs.create_completed",
                        "docs.insert_started",
                        "docs.insert_completed",
                        "drive.go_to_doc",
                    ]
                )
            if step.tool_id in ("workspace.sheets.track_step", "workspace.sheets.append"):
                expected.extend(
                    [
                        "sheets.create_started",
                        "sheets.create_completed",
                        "sheets.append_started",
                        "sheets.append_completed",
                        "drive.go_to_sheet",
                    ]
                )
        return list(dict.fromkeys(expected))

    def _build_execution_prompt(
        self,
        *,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> str:
        base = " ".join(str(request.message or "").split()).strip()
        context_summary = " ".join(
            str(settings.get("__conversation_summary") or "").split()
        ).strip()
        snippets_raw = settings.get("__conversation_snippets")
        snippets = (
            [str(item).strip() for item in snippets_raw if str(item).strip()]
            if isinstance(snippets_raw, list)
            else []
        )
        if not context_summary and not snippets:
            return base
        lines = [base]
        if context_summary:
            lines.append(f"Conversation context: {context_summary}")
        if snippets:
            lines.append("Recent snippets:")
            lines.extend(f"- {snippet}" for snippet in snippets[-6:])
        prompt = "\n".join(lines).strip()
        return prompt[:2400]

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
            metadata={
                **task_intelligence.to_dict(),
                "preferences": user_preferences,
                "conversation_context_summary": str(settings.get("__conversation_summary") or "").strip()[:480],
                "conversation_snippets": (
                    [
                        str(item).strip()
                        for item in (settings.get("__conversation_snippets") or [])
                        if str(item).strip()
                    ][:8]
                    if isinstance(settings.get("__conversation_snippets"), list)
                    else []
                ),
            },
        )
        yield _stream_event(task_understanding_ready)
        conversation_summary_text = str(settings.get("__conversation_summary") or "").strip()
        if conversation_summary_text:
            llm_context_event = self._activity_event(
                run_id=run_id,
                event_type="llm.context_summary",
                title="LLM contextual grounding",
                detail=_compact(conversation_summary_text, 180),
                metadata={"conversation_summary": conversation_summary_text},
            )
            yield _stream_event(llm_context_event)
        if task_intelligence.intent_tags:
            llm_intent_event = self._activity_event(
                run_id=run_id,
                event_type="llm.intent_tags",
                title="LLM intent classification",
                detail=", ".join(list(task_intelligence.intent_tags)[:8]),
                metadata={"intent_tags": list(task_intelligence.intent_tags)},
            )
            yield _stream_event(llm_intent_event)

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

        conversation_summary = " ".join(str(settings.get("__conversation_summary") or "").split()).strip()
        rewrite_started_event = self._activity_event(
            run_id=run_id,
            event_type="llm.task_rewrite_started",
            title="Rewriting task into detailed brief",
            detail=_compact(request.message, 200),
            metadata={"agent_goal": str(request.agent_goal or "").strip()[:240]},
        )
        yield _stream_event(rewrite_started_event)
        rewrite_payload = rewrite_task_for_execution(
            message=request.message,
            agent_goal=request.agent_goal,
            conversation_summary=conversation_summary,
        )
        rewritten_task = " ".join(
            str(rewrite_payload.get("detailed_task") or request.message or "").split()
        ).strip()
        planned_deliverables = [
            str(item).strip()
            for item in (rewrite_payload.get("deliverables") if isinstance(rewrite_payload, dict) else [])
            if str(item).strip()
        ][:6]
        planned_constraints = [
            str(item).strip()
            for item in (rewrite_payload.get("constraints") if isinstance(rewrite_payload, dict) else [])
            if str(item).strip()
        ][:6]
        rewrite_completed_event = self._activity_event(
            run_id=run_id,
            event_type="llm.task_rewrite_completed",
            title="Task rewrite ready",
            detail=_compact(rewritten_task or request.message, 220),
            metadata={
                "detailed_task": rewritten_task or request.message,
                "deliverables": planned_deliverables,
                "constraints": planned_constraints,
            },
        )
        yield _stream_event(rewrite_completed_event)

        contract_started_event = self._activity_event(
            run_id=run_id,
            event_type="llm.task_contract_started",
            title="Building task contract",
            detail="Extracting required outputs, facts, and action gates",
            metadata={"intent_tags": list(task_intelligence.intent_tags)},
        )
        yield _stream_event(contract_started_event)
        task_contract = build_task_contract(
            message=request.message,
            agent_goal=request.agent_goal,
            rewritten_task=rewritten_task,
            deliverables=planned_deliverables,
            constraints=planned_constraints,
            intent_tags=list(task_intelligence.intent_tags),
            conversation_summary=conversation_summary,
        )
        contract_objective = " ".join(str(task_contract.get("objective") or "").split()).strip()
        contract_outputs = [
            str(item).strip()
            for item in (task_contract.get("required_outputs") if isinstance(task_contract.get("required_outputs"), list) else [])
            if str(item).strip()
        ][:6]
        contract_facts = [
            str(item).strip()
            for item in (task_contract.get("required_facts") if isinstance(task_contract.get("required_facts"), list) else [])
            if str(item).strip()
        ][:6]
        contract_actions = [
            str(item).strip()
            for item in (task_contract.get("required_actions") if isinstance(task_contract.get("required_actions"), list) else [])
            if str(item).strip()
        ][:6]
        contract_missing_requirements = [
            str(item).strip()
            for item in (
                task_contract.get("missing_requirements")
                if isinstance(task_contract.get("missing_requirements"), list)
                else []
            )
            if str(item).strip()
        ][:6]
        contract_success_checks = [
            str(item).strip()
            for item in (
                task_contract.get("success_checks")
                if isinstance(task_contract.get("success_checks"), list)
                else []
            )
            if str(item).strip()
        ][:8]
        contract_target = " ".join(str(task_contract.get("delivery_target") or "").split()).strip()
        contract_completed_event = self._activity_event(
            run_id=run_id,
            event_type="llm.task_contract_completed",
            title="Task contract ready",
            detail=_compact(contract_objective or rewritten_task or request.message, 200),
            metadata={
                "objective": contract_objective,
                "required_outputs": contract_outputs,
                "required_facts": contract_facts,
                "required_actions": contract_actions,
                "delivery_target": contract_target,
                "missing_requirements": contract_missing_requirements,
                "success_checks": contract_success_checks,
            },
        )
        yield _stream_event(contract_completed_event)

        clarification_gate_enabled = _truthy(
            settings.get("agent.clarification_gate_enabled"),
            default=True,
        )
        clarification_blocked = clarification_gate_enabled and bool(contract_missing_requirements)
        clarification_questions = [
            f"Please provide: {item}"
            for item in contract_missing_requirements[:6]
        ]
        if clarification_blocked:
            clarification_event = self._activity_event(
                run_id=run_id,
                event_type="llm.clarification_requested",
                title="Clarification required before execution",
                detail=_compact("; ".join(contract_missing_requirements[:3]), 200),
                metadata={
                    "missing_requirements": contract_missing_requirements[:6],
                    "questions": clarification_questions[:6],
                },
            )
            yield _stream_event(clarification_event)
        else:
            clarification_resolved_event = self._activity_event(
                run_id=run_id,
                event_type="llm.clarification_resolved",
                title="Clarification requirements satisfied",
                detail="Execution can proceed with current contract inputs.",
                metadata={"missing_requirements": []},
            )
            yield _stream_event(clarification_resolved_event)

        planning_request = request
        planning_message_lines = [rewritten_task or request.message.strip()]
        if contract_objective:
            planning_message_lines.append("Contract objective: " + contract_objective)
        if contract_outputs:
            planning_message_lines.append("Required outputs: " + "; ".join(contract_outputs[:6]))
        if contract_facts:
            planning_message_lines.append("Required facts: " + "; ".join(contract_facts[:6]))
        if contract_success_checks:
            planning_message_lines.append("Success checks: " + "; ".join(contract_success_checks[:6]))
        if planned_deliverables:
            planning_message_lines.append(
                "Deliverables: " + "; ".join(planned_deliverables[:6])
            )
        if planned_constraints:
            planning_message_lines.append(
                "Constraints: " + "; ".join(planned_constraints[:6])
            )
        if conversation_summary:
            planning_message_lines.append(f"Conversation context: {conversation_summary}")
        planning_message = "\n".join([item for item in planning_message_lines if item]).strip()[:1600]
        if planning_message:
            try:
                planning_request = request.model_copy(update={"message": planning_message})
            except Exception:
                planning_request = request

        plan_decompose_started_event = self._activity_event(
            run_id=run_id,
            event_type="llm.plan_decompose_started",
            title="Breaking rewritten task into execution steps",
            detail=_compact(planning_message or request.message, 200),
            metadata={
                "detailed_task": rewritten_task or request.message,
                "deliverables": planned_deliverables,
                "constraints": planned_constraints,
            },
        )
        yield _stream_event(plan_decompose_started_event)
        steps = build_plan(planning_request)
        plan_decompose_completed_event = self._activity_event(
            run_id=run_id,
            event_type="llm.plan_decompose_completed",
            title="Step decomposition ready",
            detail=f"Generated {len(steps)} initial step(s).",
            metadata={"step_count": len(steps), "tool_ids": [step.tool_id for step in steps]},
        )
        yield _stream_event(plan_decompose_completed_event)
        intent_tags = set(task_intelligence.intent_tags)
        if "highlight_extract" in intent_tags and not any(
            step.tool_id == "documents.highlight.extract" for step in steps
        ):
            insertion = 1 if steps and steps[0].tool_id == "browser.playwright.inspect" else 0
            steps.insert(
                insertion,
                PlannedStep(
                    tool_id="documents.highlight.extract",
                    title="Highlight words in selected files",
                    params={},
                ),
            )
        if "docs_write" in intent_tags and not any(
            step.tool_id in ("docs.create", "workspace.docs.research_notes", "workspace.docs.fill_template")
            for step in steps
        ):
            steps.append(
                PlannedStep(
                    tool_id="workspace.docs.research_notes",
                    title="Write findings to Google Docs",
                    params={"note": request.message},
                )
            )
        if "sheets_update" in intent_tags and not any(
            step.tool_id in ("workspace.sheets.track_step", "workspace.sheets.append")
            for step in steps
        ):
            steps.insert(
                0,
                PlannedStep(
                    tool_id="workspace.sheets.track_step",
                    title="Track roadmap step in Google Sheets",
                    params={
                        "step_name": "Intent-classified roadmap step",
                        "status": "planned",
                        "detail": request.message[:320],
                    },
                ),
            )
        deep_research_mode = is_deep_research_request(request)
        highlight_color = " ".join(str(settings.get("agent.default_highlight_color") or "yellow").split()).strip().lower()
        if highlight_color not in {"yellow", "green"}:
            highlight_color = "yellow"
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

        probe_allowed_tool_ids: list[str] = []
        for tool_id in sorted(list(LLM_ALLOWED_TOOL_IDS)):
            try:
                tool_meta = self.registry.get(tool_id).metadata
            except Exception:
                continue
            if tool_meta.action_class in {"read", "draft"}:
                probe_allowed_tool_ids.append(tool_id)
        probe_rows = propose_fact_probe_steps(
            contract=task_contract,
            request_message=request.message,
            target_url=task_intelligence.target_url or "",
            existing_steps=[
                {"tool_id": item.tool_id, "title": item.title, "params": item.params}
                for item in steps[:20]
            ],
            allowed_tool_ids=probe_allowed_tool_ids,
            max_steps=4,
        )
        existing_plan_signatures: set[str] = set()
        for item in steps:
            try:
                signature = f"{item.tool_id}:{json.dumps(item.params, ensure_ascii=True, sort_keys=True)}"
            except Exception:
                signature = f"{item.tool_id}:{str(item.params)}"
            existing_plan_signatures.add(signature)
        probe_steps: list[PlannedStep] = []
        for row in probe_rows:
            tool_id = str(row.get("tool_id") or "").strip()
            if not tool_id:
                continue
            params = row.get("params")
            params_dict = dict(params) if isinstance(params, dict) else {}
            try:
                signature = f"{tool_id}:{json.dumps(params_dict, ensure_ascii=True, sort_keys=True)}"
            except Exception:
                signature = f"{tool_id}:{str(params_dict)}"
            if signature in existing_plan_signatures:
                continue
            existing_plan_signatures.add(signature)
            probe_steps.append(
                PlannedStep(
                    tool_id=tool_id,
                    title=str(row.get("title") or f"Fact probe: {tool_id}"),
                    params=params_dict,
                )
            )
            if len(probe_steps) >= 4:
                break
        if probe_steps:
            insert_at = len(steps)
            for idx, planned in enumerate(steps):
                if planned.tool_id in ("report.generate", "docs.create", "workspace.docs.research_notes"):
                    insert_at = idx
                    break
            steps[insert_at:insert_at] = probe_steps
        evidence_tool_ids = {
            "browser.playwright.inspect",
            "marketing.web_research",
            "workspace.drive.search",
            "documents.highlight.extract",
            "data.dataset.analyze",
            "sheets.read",
            "workspace.sheets.append",
        }
        has_evidence_path = any(step.tool_id in evidence_tool_ids for step in steps)
        if contract_facts and not has_evidence_path:
            evidence_step: PlannedStep
            if task_intelligence.target_url:
                evidence_step = PlannedStep(
                    tool_id="browser.playwright.inspect",
                    title="Collect evidence for required facts",
                    params={"url": task_intelligence.target_url, "highlight_color": highlight_color},
                    why_this_step="Required facts need direct evidence before final delivery.",
                    expected_evidence=tuple(contract_facts[:3]),
                )
            else:
                evidence_step = PlannedStep(
                    tool_id="marketing.web_research",
                    title="Collect evidence for required facts",
                    params={"query": request.message},
                    why_this_step="Required facts need sourced evidence before final delivery.",
                    expected_evidence=tuple(contract_facts[:3]),
                )
            steps.insert(0, evidence_step)

        workspace_logging_requested = bool(
            ("create_document" in contract_actions)
            or ("update_sheet" in contract_actions)
            or ("docs_write" in set(task_intelligence.intent_tags))
            or ("sheets_update" in set(task_intelligence.intent_tags))
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
            blueprint_search_terms = planned_search_terms[:8]
            blueprint_keywords = planned_keywords[:12]
            blueprint_lines: list[str] = [
                "# Execution Blueprint",
                "",
                "## Objective",
                f"- {contract_objective or rewritten_task or request.message}",
                "",
                "## Search Terms",
            ]
            if blueprint_search_terms:
                blueprint_lines.extend([f"- {term}" for term in blueprint_search_terms])
            else:
                blueprint_lines.append("- n/a")
            blueprint_lines.extend(["", "## Keywords"])
            if blueprint_keywords:
                blueprint_lines.extend([f"- {keyword}" for keyword in blueprint_keywords])
            else:
                blueprint_lines.append("- n/a")
            blueprint_lines.extend(["", "## Planned Workflow"])
            if steps:
                for plan_index, planned in enumerate(steps[:10], start=1):
                    blueprint_lines.append(
                        f"- {plan_index}. {planned.title} (`{planned.tool_id}`)"
                    )
            else:
                blueprint_lines.append("- n/a")
            planning_blueprint_note = "\n".join(blueprint_lines).strip()
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
                        "note": planning_blueprint_note,
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

        for idx, planned_step in enumerate(steps, start=1):
            plan_step_event = self._activity_event(
                run_id=run_id,
                event_type="llm.plan_step",
                title=f"Planned step {idx}",
                detail=f"{planned_step.title} ({planned_step.tool_id})",
                metadata={
                    "step": idx,
                    "title": planned_step.title,
                    "tool_id": planned_step.tool_id,
                    "params": planned_step.params,
                    "why_this_step": planned_step.why_this_step,
                    "expected_evidence": list(planned_step.expected_evidence),
                },
            )
            yield _stream_event(plan_step_event)

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
                    "detailed_task": rewritten_task or request.message,
                    "deliverables": planned_deliverables[:6],
                    "constraints": planned_constraints[:6],
                    "contract_objective": contract_objective,
                    "contract_required_outputs": contract_outputs[:6],
                    "contract_required_facts": contract_facts[:6],
                    "contract_required_actions": contract_actions[:6],
                    "contract_delivery_target": contract_target,
                    "contract_missing_requirements": contract_missing_requirements[:6],
                    "contract_success_checks": contract_success_checks[:8],
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
                "__intent_tags": list(task_intelligence.intent_tags),
                "__task_rewrite_detail": rewritten_task,
                "__task_rewrite_deliverables": planned_deliverables,
                "__task_rewrite_constraints": planned_constraints,
                "__task_contract": task_contract,
                "__task_contract_check": {},
                "__task_contract_success_checks": contract_success_checks[:8],
                "__task_clarification_missing": contract_missing_requirements[:6],
                "__task_clarification_questions": clarification_questions[:6],
                "__clarification_blocked": clarification_blocked,
                "__conversation_summary": str(settings.get("__conversation_summary") or "").strip()[:480],
                "__conversation_snippets": (
                    [
                        str(item).strip()
                        for item in (settings.get("__conversation_snippets") or [])
                        if str(item).strip()
                    ][:8]
                    if isinstance(settings.get("__conversation_snippets"), list)
                    else []
                ),
            },
        )

        all_actions: list[AgentAction] = []
        all_sources: list[AgentSource] = []
        next_steps: list[str] = []
        executed_steps: list[dict[str, Any]] = []
        if clarification_blocked and steps:
            clarification_block_event = self._activity_event(
                run_id=run_id,
                event_type="policy_blocked",
                title="Execution paused for clarification",
                detail=_compact("; ".join(contract_missing_requirements[:4]), 200),
                metadata={
                    "missing_requirements": contract_missing_requirements[:6],
                    "questions": clarification_questions[:6],
                },
            )
            yield _stream_event(clarification_block_event)
            next_steps.extend(clarification_questions[:6])
            steps = []
        execution_prompt = self._build_execution_prompt(request=request, settings=settings)
        contract_check_result: dict[str, Any] = {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }
        remediation_attempts = 0
        max_remediation_attempts = 2
        remediation_signatures: set[str] = set()

        def _action_rows_for_contract_check() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for action in all_actions[-24:]:
                rows.append(
                    {
                        "tool_id": action.tool_id,
                        "status": action.status,
                        "summary": action.summary,
                        "metadata": action.metadata if isinstance(action.metadata, dict) else {},
                    }
                )
            return rows

        def _source_rows_for_contract_check() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for source in all_sources[:24]:
                rows.append(
                    {
                        "label": str(source.label or "").strip(),
                        "url": str(source.url or "").strip(),
                        "score": source.score,
                        "metadata": source.metadata if isinstance(source.metadata, dict) else {},
                    }
                )
            return rows

        def _run_contract_check_live(
            *,
            phase: str,
        ) -> Generator[dict[str, Any], None, dict[str, Any]]:
            check_started = self._activity_event(
                run_id=run_id,
                event_type="llm.delivery_check_started",
                title="Verifying task contract",
                detail=f"Contract check phase: {phase}",
                metadata={"phase": phase},
            )
            yield _stream_event(check_started)
            report_body = str(execution_context.settings.get("__latest_report_content") or "").strip()
            check = verify_task_contract_fulfillment(
                contract=task_contract,
                request_message=request.message,
                executed_steps=executed_steps,
                actions=_action_rows_for_contract_check(),
                report_body=report_body,
                sources=_source_rows_for_contract_check(),
                allowed_tool_ids=sorted(list(LLM_ALLOWED_TOOL_IDS)),
            )
            execution_context.settings["__task_contract_check"] = check
            missing = (
                [str(item).strip() for item in check.get("missing_items", []) if str(item).strip()]
                if isinstance(check.get("missing_items"), list)
                else []
            )
            ready_final = bool(check.get("ready_for_final_response"))
            ready_actions = bool(check.get("ready_for_external_actions"))
            if ready_final and ready_actions:
                check_completed = self._activity_event(
                    run_id=run_id,
                    event_type="llm.delivery_check_completed",
                    title="Task contract satisfied",
                    detail="Run is ready for final response and execute actions.",
                    metadata={"phase": phase, "missing_items": []},
                )
                yield _stream_event(check_completed)
            else:
                detail = (
                    f"Missing: {', '.join(missing[:4])}"
                    if missing
                    else "Contract requirements are not fully satisfied yet."
                )
                check_failed = self._activity_event(
                    run_id=run_id,
                    event_type="llm.delivery_check_failed",
                    title="Task contract not yet satisfied",
                    detail=detail,
                    metadata={
                        "phase": phase,
                        "ready_for_final_response": ready_final,
                        "ready_for_external_actions": ready_actions,
                        "missing_items": missing[:8],
                        "reason": str(check.get("reason") or "").strip()[:260],
                    },
                )
                yield _stream_event(check_failed)
            return check

        def _build_contract_remediation_steps(
            check: dict[str, Any],
            *,
            allow_execute: bool = False,
            limit: int = 3,
        ) -> list[PlannedStep]:
            rows = check.get("recommended_remediation")
            if not isinstance(rows, list):
                return []
            suggested_steps: list[PlannedStep] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tool_id = str(row.get("tool_id") or "").strip()
                if not tool_id or tool_id not in LLM_ALLOWED_TOOL_IDS:
                    continue
                params_raw = row.get("params")
                params = dict(params_raw) if isinstance(params_raw, dict) else {}
                try:
                    signature = f"{tool_id}:{json.dumps(params, sort_keys=True, ensure_ascii=True)}"
                except Exception:
                    signature = f"{tool_id}:{str(params)}"
                if signature in remediation_signatures:
                    continue
                tool_meta = self.registry.get(tool_id).metadata
                if not allow_execute and tool_meta.action_class == "execute":
                    continue
                title = " ".join(str(row.get("title") or tool_id).split()).strip()[:120]
                remediation_signatures.add(signature)
                suggested_steps.append(
                    PlannedStep(
                        tool_id=tool_id,
                        title=f"Contract remediation: {title or tool_id}",
                        params=params,
                    )
                )
                if len(suggested_steps) >= max(1, int(limit)):
                    break
            return suggested_steps

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
            is_guarded_action = step.tool_id in GUARDED_ACTION_TOOL_IDS
            if is_guarded_action:
                contract_check_result = yield from _run_contract_check_live(
                    phase=f"before_action_step_{index}",
                )
                ready_for_actions = bool(contract_check_result.get("ready_for_external_actions"))
                if not ready_for_actions:
                    remediation_steps: list[PlannedStep] = []
                    if remediation_attempts < max_remediation_attempts:
                        remediation_steps = _build_contract_remediation_steps(
                            contract_check_result,
                            allow_execute=False,
                            limit=3,
                        )
                    if remediation_steps:
                        remediation_attempts += 1
                        steps[step_cursor:step_cursor] = remediation_steps
                        remediation_event = self._activity_event(
                            run_id=run_id,
                            event_type="plan_refined",
                            title="Inserted contract remediation steps",
                            detail=(
                                f"Added {len(remediation_steps)} remediation step(s) "
                                f"before '{step.title}'."
                            ),
                            metadata={
                                "inserted": len(remediation_steps),
                                "at_step": index,
                                "tool_ids": [item.tool_id for item in remediation_steps],
                            },
                        )
                        yield _stream_event(remediation_event)
                        continue
                    missing = (
                        [str(item).strip() for item in contract_check_result.get("missing_items", []) if str(item).strip()]
                        if isinstance(contract_check_result.get("missing_items"), list)
                        else []
                    )
                    blocked_summary = (
                        "contract_gate_blocked: "
                        + (
                            ", ".join(missing[:4])
                            if missing
                            else str(contract_check_result.get("reason") or "task contract not satisfied")
                        )
                    )
                    blocked_event = self._activity_event(
                        run_id=run_id,
                        event_type="policy_blocked",
                        title=f"Blocked by task contract: {step.title}",
                        detail=_compact(blocked_summary, 200),
                        metadata={"tool_id": step.tool_id, "step": index, "missing_items": missing[:8]},
                    )
                    yield _stream_event(blocked_event)
                    all_actions.append(
                        self.registry.get(step.tool_id).to_action(
                            status="failed",
                            summary=blocked_summary,
                            started_at=step_started,
                            metadata={"step": index, "contract_blocked": True, "missing_items": missing[:8]},
                        )
                    )
                    executed_steps.append(
                        {
                            "step": index,
                            "tool_id": step.tool_id,
                            "title": step.title,
                            "status": "failed",
                            "summary": blocked_summary,
                        }
                    )
                    step_cursor += 1
                    continue
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
                    prompt=execution_prompt,
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
                llm_step = summarize_step_outcome(
                    request_message=execution_prompt,
                    tool_id=step.tool_id,
                    step_title=step.title,
                    result_summary=result.summary,
                    result_data=result.data if isinstance(result.data, dict) else {},
                )
                llm_step_summary = str(llm_step.get("summary") or "").strip()
                llm_step_suggestion = str(llm_step.get("suggestion") or "").strip()
                if llm_step_suggestion and llm_step_suggestion not in next_steps:
                    next_steps.append(llm_step_suggestion)
                    suggestion_event = self._activity_event(
                        run_id=run_id,
                        event_type="tool_progress",
                        title="LLM context suggestion",
                        detail=llm_step_suggestion,
                        metadata={"tool_id": step.tool_id, "step": index, "llm_suggestion": True},
                    )
                    yield _stream_event(suggestion_event)
                if llm_step_summary:
                    llm_step_event = self._activity_event(
                        run_id=run_id,
                        event_type="llm.step_summary",
                        title="LLM step summary",
                        detail=llm_step_summary,
                        metadata={"tool_id": step.tool_id, "step": index},
                    )
                    yield _stream_event(llm_step_event)
                completed_event = self._activity_event(
                    run_id=run_id,
                    event_type="tool_completed",
                    title=f"Completed: {step.title}",
                    detail=llm_step_summary or result.summary,
                    metadata={
                        "tool_id": step.tool_id,
                        "step": index,
                        "llm_step_summary": llm_step_summary,
                        "llm_step_suggestion": llm_step_suggestion,
                    },
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
                                prompt=execution_prompt,
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
                    request_message=execution_prompt,
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

        delivery_requested = bool(
            task_intelligence.requires_delivery
            and task_intelligence.delivery_email
            and not clarification_blocked
        )
        delivery_attempted = any(item.tool_id in DELIVERY_ACTION_IDS for item in all_actions)
        if delivery_requested and not delivery_attempted:
            delivery_step = len(executed_steps) + 1
            delivery_started = utc_now().isoformat()
            delivery_tool_id = "mailer.report_send"
            delivery_title = "Send report email (server-side)"
            contract_check_result = yield from _run_contract_check_live(
                phase="before_server_delivery",
            )
            if not bool(contract_check_result.get("ready_for_external_actions")):
                missing = (
                    [str(item).strip() for item in contract_check_result.get("missing_items", []) if str(item).strip()]
                    if isinstance(contract_check_result.get("missing_items"), list)
                    else []
                )
                blocked_summary = (
                    "contract_gate_blocked: "
                    + (
                        ", ".join(missing[:4])
                        if missing
                        else str(contract_check_result.get("reason") or "task contract not satisfied")
                    )
                )
                blocked_event = self._activity_event(
                    run_id=run_id,
                    event_type="policy_blocked",
                    title=f"Blocked by task contract: {delivery_title}",
                    detail=_compact(blocked_summary, 200),
                    metadata={"tool_id": delivery_tool_id, "step": delivery_step, "missing_items": missing[:8]},
                )
                yield _stream_event(blocked_event)
                all_actions.append(
                    AgentAction(
                        tool_id=delivery_tool_id,
                        action_class="execute",
                        status="failed",
                        summary=blocked_summary,
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
                        "summary": blocked_summary,
                    }
                )
                if missing:
                    for item in missing[:6]:
                        if item and item not in next_steps:
                            next_steps.append(item)
                else:
                    blocked_reason = " ".join(
                        str(contract_check_result.get("reason") or "").split()
                    ).strip()
                    if blocked_reason and blocked_reason not in next_steps:
                        next_steps.append(blocked_reason)
                delivery_attempted = True
            else:

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
                required_facts_for_delivery = (
                    [str(item).strip() for item in task_contract.get("required_facts", []) if str(item).strip()]
                    if isinstance(task_contract, dict) and isinstance(task_contract.get("required_facts"), list)
                    else []
                )
                delivery_intent_tags = set(task_intelligence.intent_tags)
                location_delivery_requested = "location_lookup" in delivery_intent_tags
                if not required_facts_for_delivery and location_delivery_requested:
                    required_facts_for_delivery = (
                        [str(item).strip() for item in contract_success_checks if str(item).strip()]
                        if isinstance(contract_success_checks, list)
                        else []
                    )[:4]
                    if not required_facts_for_delivery and task_intelligence.objective:
                        required_facts_for_delivery = [str(task_intelligence.objective).strip()[:220]]
                if location_delivery_requested and required_facts_for_delivery:
                    location_brief = build_location_delivery_brief(
                        request_message=request.message,
                        objective=task_intelligence.objective,
                        report_body=report_body,
                        browser_findings=(
                            execution_context.settings.get("__latest_browser_findings")
                            if isinstance(execution_context.settings.get("__latest_browser_findings"), dict)
                            else {}
                        ),
                        sources=[
                            {
                                "label": str(source.label or "").strip(),
                                "url": str(source.url or "").strip(),
                                "metadata": source.metadata if isinstance(source.metadata, dict) else {},
                            }
                            for source in all_sources[:12]
                        ],
                    )
                    location_summary = " ".join(str(location_brief.get("summary") or "").split()).strip()
                    location_address = " ".join(str(location_brief.get("address") or "").split()).strip()
                    location_urls = (
                        [str(item).strip() for item in location_brief.get("evidence_urls", []) if str(item).strip()]
                        if isinstance(location_brief.get("evidence_urls"), list)
                        else []
                    )
                    location_confidence = " ".join(str(location_brief.get("confidence") or "").split()).strip()
                    if location_summary:
                        location_lines = [
                            "## Required Fact Findings",
                            f"- Summary: {location_summary}",
                        ]
                        if location_address:
                            location_lines.append(f"- Extracted detail: {location_address}")
                        if location_confidence:
                            location_lines.append(f"- Confidence: {location_confidence}")
                        for url in location_urls[:4]:
                            location_lines.append(f"- Evidence URL: {url}")
                        report_body = "\n".join([report_body.strip(), "", *location_lines]).strip()
                        location_event = self._activity_event(
                            run_id=run_id,
                            event_type="llm.location_brief",
                            title="LLM fact synthesis",
                            detail=_compact(location_summary, 180),
                            metadata={
                                "summary": location_summary,
                                "extracted_detail": location_address,
                                "evidence_urls": location_urls[:4],
                                "confidence": location_confidence or "unknown",
                                "required_facts": required_facts_for_delivery[:6],
                            },
                        )
                        yield _stream_event(location_event)
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

        contract_check_result = yield from _run_contract_check_live(
            phase="before_final_response",
        )
        final_missing_items = (
            [str(item).strip() for item in contract_check_result.get("missing_items", []) if str(item).strip()]
            if isinstance(contract_check_result.get("missing_items"), list)
            else []
        )
        execution_context.settings["__task_contract_check"] = contract_check_result
        if final_missing_items:
            execution_context.settings["__task_contract_missing_items"] = final_missing_items[:8]
            for item in final_missing_items[:8]:
                if item and item not in next_steps:
                    next_steps.append(item)
        final_reason = " ".join(str(contract_check_result.get("reason") or "").split()).strip()
        if final_reason:
            execution_context.settings["__task_contract_reason"] = final_reason[:320]

        unique_next_steps = curate_next_steps_for_task(
            request_message=request.message,
            task_contract=task_contract,
            candidate_steps=next_steps,
            executed_steps=executed_steps,
            actions=_action_rows_for_contract_check(),
            max_items=8,
        )

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
