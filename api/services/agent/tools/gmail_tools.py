from __future__ import annotations

import re
from typing import Any, Generator

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
SUBJECT_PATTERN = re.compile(r"(?:subject[:=]|\bsubject\b)\s*['\"]?([^'\n\"]+)", re.IGNORECASE)


def _extract_email(text: str) -> str:
    match = EMAIL_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def _extract_subject(text: str, default: str = "Company update") -> str:
    match = SUBJECT_PATTERN.search(text)
    if not match:
        return default
    subject = match.group(1).strip()
    return subject or default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _infer_dry_run(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "dry run",
            "dry-run",
            "preview only",
            "do not send",
            "don't send",
            "dont send",
            "test only",
        )
    )


def _chunk_text(text: str, *, chunk_size: int = 140, max_chunks: int = 8) -> list[str]:
    compact = " ".join(str(text or "").split())
    if not compact:
        return []
    chunks: list[str] = []
    cursor = 0
    size = max(30, int(chunk_size))
    while cursor < len(compact) and len(chunks) < max(1, int(max_chunks)):
        chunks.append(compact[cursor : cursor + size])
        cursor += size
    if cursor < len(compact):
        chunks[-1] = f"{chunks[-1]}..."
    return chunks


class GmailDraftTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="gmail.draft",
        action_class="draft",
        risk_level="medium",
        required_permissions=["gmail.draft"],
        execution_policy="auto_execute",
        description="Create Gmail draft via Gmail API.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
        to = str(params.get("to") or _extract_email(prompt)).strip()
        if not to:
            raise ToolExecutionError("`to` is required for Gmail draft.")
        report_title = str(context.settings.get("__latest_report_title") or "").strip()
        report_content = str(context.settings.get("__latest_report_content") or "").strip()
        subject = str(params.get("subject") or report_title or _extract_subject(prompt)).strip()
        body = str(params.get("body") or report_content or prompt).strip() or "No message provided."
        sender = str(params.get("from") or "").strip()

        trace_events: list[ToolTraceEvent] = []
        open_compose_event = ToolTraceEvent(
            event_type="email_open_compose",
            title="Open Gmail compose window",
            detail="Preparing draft surface",
        )
        trace_events.append(open_compose_event)
        yield open_compose_event
        draft_create_event = ToolTraceEvent(event_type="email_draft_create", title="Create Gmail draft", detail=to)
        trace_events.append(draft_create_event)
        yield draft_create_event
        recipient_event = ToolTraceEvent(event_type="email_set_to", title="Apply recipient", detail=to)
        trace_events.append(recipient_event)
        yield recipient_event
        subject_event = ToolTraceEvent(event_type="email_set_subject", title="Apply subject", detail=subject)
        trace_events.append(subject_event)
        yield subject_event
        body_chunks = _chunk_text(body, chunk_size=160, max_chunks=10)
        for chunk_index, chunk in enumerate(body_chunks, start=1):
            body_event = ToolTraceEvent(
                event_type="email_type_body",
                title=f"Type email body {chunk_index}/{len(body_chunks)}",
                detail=chunk,
                data={"chunk_index": chunk_index, "chunk_total": len(body_chunks), "typed_preview": chunk},
            )
            trace_events.append(body_event)
            yield body_event
        composed_event = ToolTraceEvent(
            event_type="email_set_body",
            title="Compose body",
            detail=f"{max(1, len(body))} characters",
            data={"typed_preview": body_chunks[-1] if body_chunks else body[:140]},
        )
        trace_events.append(composed_event)
        yield composed_event

        connector = get_connector_registry().build("gmail", settings=context.settings)
        response = connector.create_draft(to=to, subject=subject, body=body, sender=sender)
        draft = response.get("draft") if isinstance(response, dict) else {}
        draft_id = str((draft or {}).get("id") or "")
        message_id = str(((draft or {}).get("message") or {}).get("id") or "")
        ready_event = ToolTraceEvent(
            event_type="email_ready_to_send",
            title="Draft ready in Gmail",
            detail=f"Draft ID: {draft_id or 'unknown'}",
        )
        trace_events.append(ready_event)
        yield ready_event

        return ToolExecutionResult(
            summary=f"Gmail draft created for {to}.",
            content=(
                f"Created Gmail draft.\n"
                f"- To: {to}\n"
                f"- Subject: {subject}\n"
                f"- Draft ID: {draft_id or 'unknown'}\n"
                f"- Message ID: {message_id or 'unknown'}"
            ),
            data={"to": to, "subject": subject, "draft_id": draft_id, "message_id": message_id},
            sources=[],
            next_steps=["Review draft in Gmail and send when ready."],
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        traces: list[ToolTraceEvent] = []
        while True:
            try:
                traces.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = traces
        return result


class GmailSendTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="gmail.send",
        action_class="execute",
        risk_level="high",
        required_permissions=["gmail.send"],
        execution_policy="confirm_before_execute",
        description="Send Gmail message via Gmail API.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
        to = str(params.get("to") or _extract_email(prompt)).strip()
        if not to:
            raise ToolExecutionError("`to` is required for Gmail send.")
        report_title = str(context.settings.get("__latest_report_title") or "").strip()
        report_content = str(context.settings.get("__latest_report_content") or "").strip()
        subject = str(params.get("subject") or report_title or _extract_subject(prompt)).strip()
        body = str(params.get("body") or report_content or prompt).strip() or "No message provided."
        sender = str(params.get("from") or "").strip()
        dry_run = _truthy(params.get("dry_run")) or _infer_dry_run(prompt)

        trace_events: list[ToolTraceEvent] = []
        open_compose_event = ToolTraceEvent(
            event_type="email_open_compose",
            title="Open Gmail compose window",
            detail="Preparing send flow",
        )
        trace_events.append(open_compose_event)
        yield open_compose_event
        recipient_event = ToolTraceEvent(event_type="email_set_to", title="Set Gmail recipient", detail=to)
        trace_events.append(recipient_event)
        yield recipient_event
        subject_event = ToolTraceEvent(event_type="email_set_subject", title="Set Gmail subject", detail=subject)
        trace_events.append(subject_event)
        yield subject_event
        body_chunks = _chunk_text(body, chunk_size=160, max_chunks=10)
        for chunk_index, chunk in enumerate(body_chunks, start=1):
            body_event = ToolTraceEvent(
                event_type="email_type_body",
                title=f"Type email body {chunk_index}/{len(body_chunks)}",
                detail=chunk,
                data={"chunk_index": chunk_index, "chunk_total": len(body_chunks), "typed_preview": chunk},
            )
            trace_events.append(body_event)
            yield body_event
        composed_event = ToolTraceEvent(
            event_type="email_set_body",
            title="Prepare Gmail body",
            detail=f"{max(1, len(body))} characters",
            data={"typed_preview": body_chunks[-1] if body_chunks else body[:140]},
        )
        trace_events.append(composed_event)
        yield composed_event

        if dry_run:
            dry_run_ready = ToolTraceEvent(
                event_type="email_ready_to_send",
                title="Dry run complete",
                detail="Message prepared but not sent",
            )
            trace_events.append(dry_run_ready)
            yield dry_run_ready
            return ToolExecutionResult(
                summary=f"Dry run prepared Gmail send to {to}.",
                content=(
                    "Gmail send dry run completed.\n"
                    f"- To: {to}\n"
                    f"- Subject: {subject}\n"
                    "- Status: not sent (dry run)"
                ),
                data={"to": to, "subject": subject, "dry_run": True},
                sources=[],
                next_steps=["Remove dry-run and confirm send to dispatch message."],
                events=trace_events,
            )

        ready_event = ToolTraceEvent(
            event_type="email_ready_to_send",
            title="Dispatch via Gmail API",
            detail="Final send request submitted",
        )
        trace_events.append(ready_event)
        yield ready_event
        click_send_event = ToolTraceEvent(
            event_type="email_click_send",
            title="Click Send",
            detail="Submitting message to Gmail API",
        )
        trace_events.append(click_send_event)
        yield click_send_event
        connector = get_connector_registry().build("gmail", settings=context.settings)
        response = connector.send_message(to=to, subject=subject, body=body, sender=sender)
        message_id = str(response.get("id") or "")
        thread_id = str(response.get("threadId") or "")
        sent_event = ToolTraceEvent(event_type="email_sent", title="Gmail message sent", detail=message_id or to)
        trace_events.append(sent_event)
        yield sent_event

        return ToolExecutionResult(
            summary=f"Gmail message sent to {to}.",
            content=(
                f"Gmail API sent the message.\n"
                f"- To: {to}\n"
                f"- Subject: {subject}\n"
                f"- Message ID: {message_id or 'unknown'}\n"
                f"- Thread ID: {thread_id or 'unknown'}"
            ),
            data={"to": to, "subject": subject, "id": message_id, "thread_id": thread_id},
            sources=[],
            next_steps=["Track replies and update lead status."],
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        traces: list[ToolTraceEvent] = []
        while True:
            try:
                traces.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = traces
        return result


class GmailSearchTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="gmail.search",
        action_class="read",
        risk_level="low",
        required_permissions=["gmail.read"],
        execution_policy="auto_execute",
        description="Search mailbox via Gmail API query.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        query = str(params.get("query") or prompt).strip()
        max_results = int(params.get("max_results") or 20)
        connector = get_connector_registry().build("gmail", settings=context.settings)
        response = connector.list_messages(query=query, max_results=max_results)
        messages = response.get("messages") if isinstance(response, dict) else []
        if not isinstance(messages, list):
            messages = []

        lines = [f"### Gmail search results ({len(messages)} message IDs)"]
        for row in messages[:20]:
            if not isinstance(row, dict):
                continue
            lines.append(f"- id: {row.get('id')} | thread: {row.get('threadId')}")
        if len(lines) == 1:
            lines.append("- No matching messages.")

        return ToolExecutionResult(
            summary=f"Gmail search returned {len(messages)} messages.",
            content="\n".join(lines),
            data={"query": query, "count": len(messages), "messages": messages},
            sources=[],
            next_steps=["Fetch full message details for targeted follow-ups."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Search Gmail mailbox",
                    detail=query or "inbox",
                    data={"query": query, "count": len(messages)},
                )
            ],
        )
