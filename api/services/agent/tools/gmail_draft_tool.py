from __future__ import annotations

from typing import Any, Generator

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.llm_execution_support import polish_email_content
from api.services.agent.tools.gmail_tools_helpers import (
    _attach_to_gmail_draft,
    _chunk_text,
    _extract_email,
    _extract_subject,
    _infer_dry_run,
    _is_invalid_email_body,
    _resolve_attachments,
    _truthy,
)

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
        from api.services.agent.tools import gmail_tools as gmail_tools_module

        to = str(params.get("to") or _extract_email(prompt)).strip()
        if not to:
            raise ToolExecutionError("`to` is required for Gmail draft.")
        report_title = str(context.settings.get("__latest_report_title") or "").strip()
        delivery_subject_hint = str(context.settings.get("__latest_delivery_email_subject") or "").strip()
        report_content = str(context.settings.get("__latest_report_content") or "").strip()
        delivery_body_hint = str(context.settings.get("__latest_delivery_email_body") or "").strip()
        explicit_subject = str(params.get("subject") or "").strip()
        explicit_body = str(params.get("body") or "").strip()
        subject = str(explicit_subject or delivery_subject_hint or report_title or _extract_subject(prompt)).strip()
        if _is_invalid_email_body(explicit_body):
            explicit_body = ""
        if _is_invalid_email_body(delivery_body_hint):
            delivery_body_hint = ""
        if _is_invalid_email_body(report_content):
            report_content = ""
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
            title="Compose body",
            detail=f"{max(1, len(body))} characters",
            data={"typed_preview": typed_preview or body},
        )
        trace_events.append(composed_event)
        yield composed_event

        connector = gmail_tools_module.get_connector_registry().build("gmail", settings=context.settings)
        response = connector.create_draft(to=to, subject=subject, body=body, sender=sender)
        draft = response.get("draft") if isinstance(response, dict) else {}
        draft_id = str((draft or {}).get("id") or "")
        message_id = str(((draft or {}).get("message") or {}).get("id") or "")
        attached_labels = yield from _attach_to_gmail_draft(
            connector=connector,
            draft_id=draft_id,
            attachments=attachments,
            trace_events=trace_events,
        )
        ready_event = ToolTraceEvent(
            event_type="email_ready_to_send",
            title="Draft ready in Gmail",
            detail=(
                f"Draft ID: {draft_id or 'unknown'}"
                if not attached_labels
                else f"Draft ID: {draft_id or 'unknown'} with {len(attached_labels)} attachment(s)"
            ),
        )
        trace_events.append(ready_event)
        yield ready_event

        attachment_lines = [f"- Attachments: {len(attached_labels)}"] if attached_labels else []
        if attached_labels:
            attachment_lines.extend([f"  - {item}" for item in attached_labels[:6]])
        return ToolExecutionResult(
            summary=f"Gmail draft created for {to}.",
            content=(
                f"Created Gmail draft.\n"
                f"- To: {to}\n"
                f"- Subject: {subject}\n"
                f"- Draft ID: {draft_id or 'unknown'}\n"
                f"- Message ID: {message_id or 'unknown'}\n"
                + ("\n".join(attachment_lines) if attachment_lines else "- Attachments: 0")
            ),
            data={
                "to": to,
                "subject": subject,
                "draft_id": draft_id,
                "message_id": message_id,
                "attachments_count": len(attached_labels),
                "attachments": attached_labels[:16],
                "delivery_mode": "gmail_api",
            },
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
