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
from api.services.agent.tools.gmail_live_desktop import (
    desktop_mode_enabled,
    desktop_mode_required,
    stream_live_desktop_compose,
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


def _compact_text(value: Any, *, limit: int = 280) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}..."


def _looks_like_path(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    if "/" in candidate or "\\" in candidate:
        return True
    if candidate.startswith("."):
        return True
    lowered = candidate.lower()
    return lowered.endswith(
        (
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".csv",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".png",
            ".jpg",
            ".jpeg",
        )
    )


def _normalize_attachment_row(item: Any) -> dict[str, str] | None:
    if isinstance(item, dict):
        local_path = str(
            item.get("local_path")
            or item.get("path")
            or item.get("pdf_path")
            or item.get("attachment_path")
            or ""
        ).strip()
        file_id = str(
            item.get("file_id")
            or item.get("document_id")
            or item.get("drive_file_id")
            or item.get("attachment_file_id")
            or ""
        ).strip()
        label = str(item.get("label") or item.get("name") or local_path or file_id).strip()
        if local_path:
            return {"local_path": local_path, "label": label or local_path}
        if file_id:
            return {"file_id": file_id, "label": label or file_id}
        return None

    text = str(item or "").strip()
    if not text:
        return None
    if _looks_like_path(text):
        return {"local_path": text, "label": text}
    return {"file_id": text, "label": text}


def _dedupe_attachments(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        local_path = str(row.get("local_path") or "").strip()
        file_id = str(row.get("file_id") or "").strip()
        if not local_path and not file_id:
            continue
        key = ("local_path", local_path) if local_path else ("file_id", file_id)
        if key in seen:
            continue
        seen.add(key)
        label = str(row.get("label") or local_path or file_id).strip() or (local_path or file_id)
        payload: dict[str, str] = {"label": label}
        if local_path:
            payload["local_path"] = local_path
        if file_id:
            payload["file_id"] = file_id
        deduped.append(payload)
    return deduped


def _resolve_attachments(
    *,
    context: ToolExecutionContext,
    params: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    raw_list = params.get("attachments")
    if isinstance(raw_list, list):
        for item in raw_list[:16]:
            normalized = _normalize_attachment_row(item)
            if normalized:
                rows.append(normalized)

    for value in (
        params.get("attachment_path"),
        params.get("local_path"),
        params.get("pdf_path"),
    ):
        normalized = _normalize_attachment_row({"local_path": value})
        if normalized:
            rows.append(normalized)

    for value in (
        params.get("attachment_file_id"),
        params.get("file_id"),
        params.get("document_id"),
    ):
        normalized = _normalize_attachment_row({"file_id": value})
        if normalized:
            rows.append(normalized)

    attach_latest_raw = params.get("attach_latest_report_pdf")
    if attach_latest_raw is None:
        attach_latest = False
    else:
        attach_latest = _truthy(attach_latest_raw)
    if attach_latest:
        latest_pdf_path = str(context.settings.get("__latest_report_pdf_path") or "").strip()
        latest_document_id = str(context.settings.get("__latest_report_document_id") or "").strip()
        if latest_pdf_path:
            rows.append(
                {
                    "local_path": latest_pdf_path,
                    "label": str(context.settings.get("__latest_report_title") or latest_pdf_path).strip()
                    or latest_pdf_path,
                }
            )
        elif latest_document_id:
            rows.append(
                {
                    "file_id": latest_document_id,
                    "label": str(context.settings.get("__latest_report_title") or latest_document_id).strip()
                    or latest_document_id,
                }
            )

    return _dedupe_attachments(rows)


def _attachment_data(row: dict[str, str]) -> dict[str, str]:
    local_path = str(row.get("local_path") or "").strip()
    file_id = str(row.get("file_id") or "").strip()
    payload = {"attachment_label": str(row.get("label") or local_path or file_id).strip()}
    if local_path:
        payload["local_path"] = local_path
    if file_id:
        payload["file_id"] = file_id
    return payload


def _attach_to_gmail_draft(
    *,
    connector: Any,
    draft_id: str,
    attachments: list[dict[str, str]],
    trace_events: list[ToolTraceEvent],
) -> Generator[ToolTraceEvent, None, list[str]]:
    labels: list[str] = []
    if not attachments:
        return labels
    if not draft_id:
        raise ToolExecutionError("Draft ID is required before adding attachments.")
    for index, row in enumerate(attachments, start=1):
        payload = _attachment_data(row)
        detail = _compact_text(payload.get("attachment_label"), limit=160)
        attach_event = ToolTraceEvent(
            event_type="email_add_attachment",
            title=f"Attach file {index}/{len(attachments)}",
            detail=detail,
            data={"draft_id": draft_id, "index": index, "total": len(attachments), **payload},
        )
        trace_events.append(attach_event)
        yield attach_event

        local_path = str(row.get("local_path") or "").strip() or None
        file_id = str(row.get("file_id") or "").strip() or None
        connector.add_attachment(
            draft_id=draft_id,
            file_id=file_id,
            local_path=local_path,
        )
        labels.append(payload.get("attachment_label") or local_path or file_id or f"attachment-{index}")
    return labels


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
        attachments = _resolve_attachments(
            context=context,
            params=params,
        )
        live_desktop = desktop_mode_enabled(context, params)
        desktop_required = desktop_mode_required(context, params)

        trace_events: list[ToolTraceEvent] = []
        if attachments and live_desktop:
            if desktop_required:
                raise ToolExecutionError(
                    "Live desktop draft does not support attachments yet. Set `live_desktop=false`."
                )
            attachment_fallback = ToolTraceEvent(
                event_type="tool_progress",
                title="Attachments require Gmail API draft flow",
                detail="Switching from live desktop to Gmail API to attach files",
                data={"attachments": len(attachments)},
            )
            trace_events.append(attachment_fallback)
            yield attachment_fallback
            live_desktop = False
        if live_desktop:
            try:
                desktop_result = yield from stream_live_desktop_compose(
                    context=context,
                    trace_events=trace_events,
                    to=to,
                    subject=subject,
                    body=body,
                    send=False,
                )
                draft_id = str(desktop_result.get("draft_id") or "")
                compose_url = str(desktop_result.get("url") or "")
                return ToolExecutionResult(
                    summary=f"Gmail draft created for {to} via live desktop session.",
                    content=(
                        "Created Gmail draft via live browser desktop.\n"
                        f"- To: {to}\n"
                        f"- Subject: {subject}\n"
                        f"- Compose URL: {compose_url or 'unknown'}\n"
                        f"- Draft ID: {draft_id or 'unknown'}"
                    ),
                    data={
                        "to": to,
                        "subject": subject,
                        "draft_id": draft_id,
                        "compose_url": compose_url,
                        "delivery_mode": "playwright_desktop",
                    },
                    sources=[],
                    next_steps=["Review draft in Gmail and send when ready."],
                    events=trace_events,
                )
            except Exception as exc:
                if desktop_required:
                    raise ToolExecutionError(f"Live Gmail desktop draft failed: {exc}") from exc
                fallback = ToolTraceEvent(
                    event_type="tool_progress",
                    title="Live desktop draft unavailable",
                    detail="Falling back to Gmail API draft flow",
                    data={"reason": str(exc)},
                )
                trace_events.append(fallback)
                yield fallback

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
        attachments = _resolve_attachments(
            context=context,
            params=params,
        )
        dry_run = _truthy(params.get("dry_run")) or _infer_dry_run(prompt)
        live_desktop = desktop_mode_enabled(context, params)
        desktop_required = desktop_mode_required(context, params)

        trace_events: list[ToolTraceEvent] = []
        if attachments and live_desktop and not dry_run:
            if desktop_required:
                raise ToolExecutionError(
                    "Live desktop send does not support attachments yet. Set `live_desktop=false`."
                )
            attachment_fallback = ToolTraceEvent(
                event_type="tool_progress",
                title="Attachments require Gmail API send flow",
                detail="Switching from live desktop to Gmail API to attach files",
                data={"attachments": len(attachments)},
            )
            trace_events.append(attachment_fallback)
            yield attachment_fallback
            live_desktop = False
        if live_desktop and not dry_run:
            try:
                desktop_result = yield from stream_live_desktop_compose(
                    context=context,
                    trace_events=trace_events,
                    to=to,
                    subject=subject,
                    body=body,
                    send=True,
                )
                compose_url = str(desktop_result.get("url") or "")
                return ToolExecutionResult(
                    summary=f"Gmail message sent to {to} via live desktop session.",
                    content=(
                        "Gmail desktop sent the message through live browser execution.\n"
                        f"- To: {to}\n"
                        f"- Subject: {subject}\n"
                        f"- Compose URL: {compose_url or 'unknown'}"
                    ),
                    data={
                        "to": to,
                        "subject": subject,
                        "id": str(desktop_result.get("message_id") or ""),
                        "thread_id": str(desktop_result.get("thread_id") or ""),
                        "compose_url": compose_url,
                        "delivery_mode": "playwright_desktop",
                    },
                    sources=[],
                    next_steps=["Track replies and update lead status."],
                    events=trace_events,
                )
            except Exception as exc:
                if desktop_required:
                    raise ToolExecutionError(f"Live Gmail desktop send failed: {exc}") from exc
                fallback = ToolTraceEvent(
                    event_type="tool_progress",
                    title="Live desktop send unavailable",
                    detail="Falling back to Gmail API send flow",
                    data={"reason": str(exc)},
                )
                trace_events.append(fallback)
                yield fallback

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
