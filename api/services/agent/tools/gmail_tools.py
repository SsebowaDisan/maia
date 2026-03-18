from __future__ import annotations

from typing import Any, Generator

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.llm_execution_support import polish_email_content
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.gmail_draft_tool import GmailDraftTool
from api.services.agent.tools.gmail_tools_helpers import (
    _attach_to_gmail_draft,
    _chunk_text,
    _compact_text,
    _extract_email,
    _extract_subject,
    _infer_dry_run,
    _resolve_attachments,
    _truthy,
)

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
        delivery_subject_hint = str(context.settings.get("__latest_delivery_email_subject") or "").strip()
        report_content = str(context.settings.get("__latest_report_content") or "").strip()
        delivery_body_hint = str(context.settings.get("__latest_delivery_email_body") or "").strip()
        explicit_subject = str(params.get("subject") or "").strip()
        explicit_body = str(params.get("body") or "").strip()
        subject = str(explicit_subject or delivery_subject_hint or report_title or _extract_subject(prompt)).strip()
        body_source = (
            "explicit"
            if explicit_body
            else "delivery_hint"
            if delivery_body_hint
            else "report_content"
            if report_content
            else "prompt"
        )
        raw_body = str(explicit_body or delivery_body_hint or report_content or prompt).strip() or "No message provided."
        if body_source in {"explicit", "delivery_hint", "report_content"}:
            body = raw_body
        else:
            polished = polish_email_content(
                subject=subject or "Company update",
                body_text=raw_body,
                recipient=to,
                context_summary=" ".join(str(prompt or "").split()).strip()[:320],
                target_format="recipient_email",
            )
            polished_subject = " ".join(str(polished.get("subject") or "").split()).strip()
            polished_body = str(polished.get("body_text") or "").strip()
            if not explicit_subject and polished_subject:
                subject = polished_subject
            body = polished_body or raw_body
        sender = str(params.get("from") or "").strip()
        attachments = _resolve_attachments(
            context=context,
            params=params,
        )
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
        body_chunks = _chunk_text(
            body,
            chunk_size=120,
            max_chunks=max(1, (len(body) // 120) + 2),
        )
        typed_preview = ""
        for chunk_index, chunk in enumerate(body_chunks, start=1):
            typed_preview += chunk
            body_event = ToolTraceEvent(
                event_type="email_type_body",
                title=f"Type email body {chunk_index}/{len(body_chunks)}",
                detail=chunk,
                data={
                    "chunk_index": chunk_index,
                    "chunk_total": len(body_chunks),
                    "typed_preview": typed_preview,
                },
            )
            trace_events.append(body_event)
            yield body_event
        composed_event = ToolTraceEvent(
            event_type="email_set_body",
            title="Prepare Gmail body",
            detail=f"{max(1, len(body))} characters",
            data={"typed_preview": typed_preview or body},
        )
        trace_events.append(composed_event)
        yield composed_event

        if dry_run:
            dry_run_ready = ToolTraceEvent(
                event_type="email_ready_to_send",
                title="Dry run complete",
                detail=(
                    "Message prepared but not sent"
                    if not attachments
                    else f"Message + {len(attachments)} attachment(s) prepared but not sent"
                ),
            )
            trace_events.append(dry_run_ready)
            yield dry_run_ready
            return ToolExecutionResult(
                summary=f"Dry run prepared Gmail send to {to}.",
                content=(
                    "Gmail send dry run completed.\n"
                    f"- To: {to}\n"
                    f"- Subject: {subject}\n"
                    f"- Attachments: {len(attachments)}\n"
                    "- Status: not sent (dry run)"
                ),
                data={
                    "to": to,
                    "subject": subject,
                    "dry_run": True,
                    "attachments_count": len(attachments),
                    "delivery_mode": "dry_run",
                },
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
        attached_labels: list[str] = []
        draft_id = ""
        if attachments:
            try:
                draft_response = connector.create_draft(to=to, subject=subject, body=body, sender=sender)
                draft = draft_response.get("draft") if isinstance(draft_response, dict) else {}
                draft_id = str((draft or {}).get("id") or "")
                attached_labels = yield from _attach_to_gmail_draft(
                    connector=connector,
                    draft_id=draft_id,
                    attachments=attachments,
                    trace_events=trace_events,
                )
                response = connector.send_draft(draft_id=draft_id)
            except Exception as exc:
                exc_text = str(exc or "")
                normalized_error = exc_text.lower()
                scope_blocked = (
                    "insufficient authentication scopes" in normalized_error
                    or "insufficientpermissions" in normalized_error
                    or "insufficient permission" in normalized_error
                )
                if not scope_blocked:
                    raise
                fallback_event = ToolTraceEvent(
                    event_type="tool_progress",
                    title="Draft API blocked by scope, using direct send fallback",
                    detail="Sending with Gmail API raw message attachment flow",
                    data={"reason": _compact_text(exc_text, limit=220)},
                )
                trace_events.append(fallback_event)
                yield fallback_event
                send_attachments: list[dict[str, str]] = []
                attached_labels = []
                for row in attachments:
                    if not isinstance(row, dict):
                        continue
                    local_path = str(row.get("local_path") or "").strip()
                    file_id = str(row.get("file_id") or "").strip()
                    label = str(row.get("label") or local_path or file_id).strip()
                    if not local_path and not file_id:
                        continue
                    payload: dict[str, str] = {}
                    if local_path:
                        payload["local_path"] = local_path
                    if file_id:
                        payload["file_id"] = file_id
                    send_attachments.append(payload)
                    attached_labels.append(label or local_path or file_id)
                    attach_event = ToolTraceEvent(
                        event_type="email_add_attachment",
                        title=f"Attach file {len(attached_labels)}/{len(attachments)}",
                        detail=_compact_text(label or local_path or file_id, limit=160),
                        data={**payload, "send_mode": "gmail_send_direct"},
                    )
                    trace_events.append(attach_event)
                    yield attach_event
                send_with_attachments = getattr(connector, "send_message_with_attachments", None)
                if not callable(send_with_attachments):
                    raise ToolExecutionError(
                        "Gmail connector does not support attachment send fallback."
                    ) from exc
                response = send_with_attachments(
                    to=to,
                    subject=subject,
                    body=body,
                    sender=sender,
                    attachments=send_attachments,
                )
        else:
            response = connector.send_message(to=to, subject=subject, body=body, sender=sender)
        message_id = str(response.get("id") or "")
        thread_id = str(response.get("threadId") or "")
        sent_event = ToolTraceEvent(event_type="email_sent", title="Gmail message sent", detail=message_id or to)
        trace_events.append(sent_event)
        yield sent_event

        attachment_lines = [f"- Attachments: {len(attached_labels)}"] if attached_labels else []
        if attached_labels:
            attachment_lines.extend([f"  - {item}" for item in attached_labels[:6]])
        return ToolExecutionResult(
            summary=f"Gmail message sent to {to}.",
            content=(
                f"Gmail API sent the message.\n"
                f"- To: {to}\n"
                f"- Subject: {subject}\n"
                f"- Message ID: {message_id or 'unknown'}\n"
                f"- Thread ID: {thread_id or 'unknown'}\n"
                + ("\n".join(attachment_lines) if attachment_lines else "- Attachments: 0")
            ),
            data={
                "to": to,
                "subject": subject,
                "id": message_id,
                "thread_id": thread_id,
                "draft_id": draft_id or None,
                "attachments_count": len(attached_labels),
                "attachments": attached_labels[:16],
                "delivery_mode": "gmail_api",
            },
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
