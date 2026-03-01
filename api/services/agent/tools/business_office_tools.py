from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.business_workflow_helpers import (
    amount_from_text,
    email_from_text,
    emails_from_text,
    invoice_number_from_text,
)
from api.services.agent.tools.document_tools import DocumentCreateTool
from api.services.agent.tools.invoice_tools import InvoiceCreateTool, InvoiceSendTool


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _default_meeting_window() -> tuple[str, str]:
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(minutes=30)
    return start.isoformat(), end.isoformat()


class BusinessInvoiceWorkflowTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="business.invoice_workflow",
        action_class="execute",
        risk_level="high",
        required_permissions=["invoice.write", "invoice.send"],
        execution_policy="confirm_before_execute",
        description="Create an invoice and optionally send it, with full theatre-visible workflow events.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        customer = str(params.get("customer") or "Customer").strip() or "Customer"
        invoice_number = str(params.get("invoice_number") or invoice_number_from_text(prompt) or "").strip()
        amount_hint = amount_from_text(str(params.get("amount") or "") or prompt)
        line_items = params.get("line_items")
        if not isinstance(line_items, list) or not line_items:
            default_amount = amount_hint if amount_hint is not None else 0.0
            line_items = [{"description": "Professional services", "quantity": 1, "unit_price": default_amount}]
        send_now = _truthy(params.get("send"), default=False)

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="tool_progress",
                title="Start invoice workflow",
                detail=invoice_number or customer,
                data={"tool_id": self.metadata.tool_id, "scene_surface": "document"},
            )
        ]

        create_tool = InvoiceCreateTool()
        create_result = create_tool.execute(
            context=context,
            prompt=prompt,
            params={
                "customer": customer,
                "invoice_number": invoice_number,
                "currency": str(params.get("currency") or "USD"),
                "due_date": str(params.get("due_date") or ""),
                "tax_rate": params.get("tax_rate", 0),
                "line_items": line_items,
            },
        )
        events.extend(create_result.events or [])

        created_invoice_number = str(create_result.data.get("invoice_number") or invoice_number or "").strip()
        spreadsheet_id = str(params.get("spreadsheet_id") or "").strip()
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit" if spreadsheet_id else ""
        if spreadsheet_id:
            workspace = get_connector_registry().build("google_workspace", settings=context.settings)
            rows = [
                [
                    "InvoiceNumber",
                    "Customer",
                    "Currency",
                    "Total",
                    "Status",
                    "PdfPath",
                ],
                [
                    created_invoice_number,
                    customer,
                    str(create_result.data.get("currency") or "USD"),
                    str(create_result.data.get("total") or ""),
                    "CREATED",
                    str(create_result.data.get("pdf_path") or ""),
                ],
            ]
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="sheet_open",
                        title="Open invoice tracker sheet",
                        detail=spreadsheet_id,
                        data={"spreadsheet_id": spreadsheet_id, "spreadsheet_url": spreadsheet_url},
                    ),
                    ToolTraceEvent(
                        event_type="sheets.append_started",
                        title="Write invoice tracker rows",
                        detail="2 row(s)",
                        data={"spreadsheet_id": spreadsheet_id, "range": "Tracker!A1", "source_url": spreadsheet_url},
                    ),
                ]
            )
            append_response = workspace.append_sheet_values(
                spreadsheet_id=spreadsheet_id,
                sheet_range=str(params.get("sheet_range") or "Tracker!A1"),
                values=rows,
            )
            updated_rows = (
                (append_response.get("updates") or {}).get("updatedRows")
                if isinstance(append_response, dict)
                else 0
            )
            events.append(
                ToolTraceEvent(
                    event_type="sheets.append_completed",
                    title="Invoice tracker rows saved",
                    detail=f"Updated rows: {updated_rows or 0}",
                    data={"spreadsheet_id": spreadsheet_id, "updated_rows": updated_rows or 0, "source_url": spreadsheet_url},
                )
            )

        send_summary = "Draft created only."
        delivery: dict[str, Any] = {"requested": send_now, "sent": False}
        if send_now:
            send_tool = InvoiceSendTool()
            try:
                send_result = send_tool.execute(
                    context=context,
                    prompt=prompt,
                    params={
                        **params,
                        "invoice_number": created_invoice_number,
                        "customer": customer,
                        "line_items": line_items,
                    },
                )
                events.extend(send_result.events or [])
                send_summary = send_result.summary
                delivery = {"requested": True, "sent": True, "response": send_result.data}
            except Exception as exc:
                events.append(
                    ToolTraceEvent(
                        event_type="tool_failed",
                        title="Invoice send failed",
                        detail=str(exc)[:220],
                        data={"tool_id": "invoice.send"},
                    )
                )
                send_summary = f"Send failed: {exc}"
                delivery = {"requested": True, "sent": False, "error": str(exc)}

        return ToolExecutionResult(
            summary=f"Invoice workflow completed for {created_invoice_number or customer}.",
            content=(
                f"{create_result.content}\n"
                f"\n### Delivery\n- {send_summary}\n"
                f"{f'- Tracker: {spreadsheet_url}' if spreadsheet_url else ''}"
            ).strip(),
            data={
                "invoice": create_result.data,
                "delivery": delivery,
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_url": spreadsheet_url,
            },
            sources=[],
            next_steps=[
                "Review totals and customer details before final dispatch.",
                "Use tracker sheet link for finance audit if provided.",
            ],
            events=events,
        )


class BusinessMeetingSchedulerTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="business.meeting_scheduler",
        action_class="execute",
        risk_level="high",
        required_permissions=["calendar.write", "docs.write"],
        execution_policy="confirm_before_execute",
        description="Schedule a business meeting and create an agenda document.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        summary = str(params.get("summary") or "Business meeting").strip() or "Business meeting"
        description = str(params.get("description") or prompt).strip()
        attendees = params.get("attendees")
        attendee_emails = [str(item).strip() for item in attendees] if isinstance(attendees, list) else emails_from_text(prompt)
        calendar_id = str(params.get("calendar_id") or "primary").strip() or "primary"
        default_start_iso, default_end_iso = _default_meeting_window()
        start_iso = str(params.get("start_iso") or default_start_iso).strip() or default_start_iso
        end_iso = str(params.get("end_iso") or default_end_iso).strip() or default_end_iso

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="tool_progress",
                title="Start meeting scheduler workflow",
                detail=summary,
                data={"tool_id": self.metadata.tool_id, "scene_surface": "system"},
            )
        ]
        calendar = get_connector_registry().build("google_calendar", settings=context.settings)
        calendar_event = calendar.create_event(
            summary=summary,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description,
            attendees=attendee_emails,
            calendar_id=calendar_id,
        )
        event_id = str(calendar_event.get("id") or "").strip()
        event_url = str(calendar_event.get("htmlLink") or "").strip()
        events.extend(
            [
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Create calendar event",
                    detail=summary,
                    data={"calendar_id": calendar_id, "attendees": attendee_emails},
                ),
                ToolTraceEvent(
                    event_type="tool_completed",
                    title="Meeting scheduled",
                    detail=event_id or summary,
                    data={"event_id": event_id, "link": event_url},
                ),
            ]
        )

        create_agenda = _truthy(params.get("create_agenda"), default=True)
        agenda_url = ""
        agenda_id = ""
        if create_agenda:
            workspace = get_connector_registry().build("google_workspace", settings=context.settings)
            agenda_title = str(params.get("agenda_title") or f"Agenda - {summary}").strip() or f"Agenda - {summary}"
            agenda_body = str(
                params.get("agenda_body")
                or f"Meeting: {summary}\n\nObjectives:\n- Confirm agenda\n- Define next actions\n\nNotes:\n{description}"
            ).strip()
            events.extend(
                [
                    ToolTraceEvent(event_type="doc_open", title="Open agenda document", detail=agenda_title),
                    ToolTraceEvent(event_type="docs.create_started", title="Create agenda doc", detail=agenda_title),
                ]
            )
            created = workspace.create_docs_document(title=agenda_title)
            agenda_id = str(created.get("documentId") or "").strip()
            agenda_url = f"https://docs.google.com/document/d/{agenda_id}/edit" if agenda_id else ""
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="docs.create_completed",
                        title="Agenda doc created",
                        detail=agenda_id or agenda_title,
                        data={"doc_id": agenda_id, "document_url": agenda_url, "source_url": agenda_url},
                    ),
                    ToolTraceEvent(
                        event_type="docs.insert_started",
                        title="Insert agenda content",
                        detail=f"{len(agenda_body)} characters",
                        data={"doc_id": agenda_id, "source_url": agenda_url},
                    ),
                ]
            )
            if agenda_id:
                workspace.docs_insert_text(document_id=agenda_id, text=f"{agenda_body}\n")
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="docs.insert_completed",
                        title="Agenda content inserted",
                        detail=agenda_id or agenda_title,
                        data={"doc_id": agenda_id, "source_url": agenda_url},
                    ),
                    ToolTraceEvent(
                        event_type="doc_save",
                        title="Save agenda document",
                        detail=agenda_id or agenda_title,
                        data={"document_id": agenda_id, "document_url": agenda_url, "source_url": agenda_url},
                    ),
                ]
            )

        return ToolExecutionResult(
            summary=f"Meeting scheduler workflow completed for {summary}.",
            content=(
                "### Meeting Scheduled\n"
                f"- Summary: {summary}\n"
                f"- Event link: {event_url or 'not available'}\n"
                f"- Attendees: {', '.join(attendee_emails) if attendee_emails else 'none'}\n"
                f"- Agenda: {agenda_url or 'not created'}"
            ),
            data={
                "event_id": event_id,
                "event_url": event_url,
                "agenda_doc_id": agenda_id,
                "agenda_doc_url": agenda_url,
                "attendees": attendee_emails,
            },
            sources=[],
            next_steps=[
                "Share the agenda link with attendees.",
                "Add meeting outcomes to notes after the session.",
            ],
            events=events,
        )


class BusinessProposalWorkflowTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="business.proposal_workflow",
        action_class="draft",
        risk_level="medium",
        required_permissions=["docs.write", "gmail.draft"],
        execution_policy="auto_execute",
        description="Create a proposal document and optionally draft an email to a stakeholder.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        title = str(params.get("title") or "Business Proposal").strip() or "Business Proposal"
        body = str(params.get("body") or prompt).strip() or "Proposal details to be finalized."
        recipient = str(params.get("to") or email_from_text(prompt)).strip()

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="tool_progress",
                title="Start proposal workflow",
                detail=title,
                data={"tool_id": self.metadata.tool_id, "scene_surface": "document"},
            )
        ]

        doc_url = ""
        doc_id = ""
        try:
            workspace = get_connector_registry().build("google_workspace", settings=context.settings)
            events.extend(
                [
                    ToolTraceEvent(event_type="doc_open", title="Open proposal document", detail=title),
                    ToolTraceEvent(event_type="docs.create_started", title="Create proposal doc", detail=title),
                ]
            )
            created = workspace.create_docs_document(title=title)
            doc_id = str(created.get("documentId") or "").strip()
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else ""
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="docs.create_completed",
                        title="Proposal doc created",
                        detail=doc_id or title,
                        data={"doc_id": doc_id, "document_url": doc_url, "source_url": doc_url},
                    ),
                    ToolTraceEvent(
                        event_type="docs.insert_started",
                        title="Insert proposal content",
                        detail=f"{len(body)} characters",
                        data={"doc_id": doc_id, "source_url": doc_url},
                    ),
                ]
            )
            if doc_id:
                workspace.docs_insert_text(document_id=doc_id, text=f"{body}\n")
            events.extend(
                [
                    ToolTraceEvent(
                        event_type="docs.insert_completed",
                        title="Proposal content inserted",
                        detail=doc_id or title,
                        data={"doc_id": doc_id, "source_url": doc_url},
                    ),
                    ToolTraceEvent(
                        event_type="doc_save",
                        title="Save proposal document",
                        detail=doc_id or title,
                        data={"document_id": doc_id, "document_url": doc_url, "source_url": doc_url},
                    ),
                ]
            )
        except Exception as exc:
            fallback_result = DocumentCreateTool().execute(
                context=context,
                prompt=body,
                params={"title": title, "body": body, "provider": "local"},
            )
            events.append(
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Google Docs unavailable, used local draft",
                    detail=str(exc)[:180],
                    data={"tool_id": self.metadata.tool_id},
                )
            )
            events.extend(fallback_result.events or [])
            doc_url = str(fallback_result.data.get("path") or "")
            doc_id = str(fallback_result.data.get("path") or "")

        draft_id = ""
        if recipient:
            subject = str(params.get("subject") or f"Proposal: {title}").strip() or f"Proposal: {title}"
            email_body = (
                f"Hello,\n\nPlease review the proposal draft.\n\nTitle: {title}\n"
                f"Link: {doc_url or 'see attached reference'}\n\nRegards,\nMaia Agent"
            )
            events.extend(
                [
                    ToolTraceEvent(event_type="email_open_compose", title="Open proposal email draft", detail=recipient),
                    ToolTraceEvent(event_type="email_draft_create", title="Create proposal draft email", detail=recipient),
                    ToolTraceEvent(event_type="email_set_to", title="Apply recipient", detail=recipient),
                    ToolTraceEvent(event_type="email_set_subject", title="Apply subject", detail=subject),
                    ToolTraceEvent(
                        event_type="email_set_body",
                        title="Compose proposal email body",
                        detail=f"{len(email_body)} characters",
                        data={"typed_preview": email_body[:160]},
                    ),
                ]
            )
            gmail = get_connector_registry().build("gmail", settings=context.settings)
            draft = gmail.create_draft(to=recipient, subject=subject, body=email_body)
            draft_id = str((draft.get("draft") or {}).get("id") or "").strip()
            events.append(
                ToolTraceEvent(
                    event_type="email_ready_to_send",
                    title="Proposal email draft ready",
                    detail=draft_id or recipient,
                )
            )

        return ToolExecutionResult(
            summary=f"Proposal workflow completed: {title}.",
            content=(
                "### Proposal Workflow\n"
                f"- Title: {title}\n"
                f"- Proposal document: {doc_url or 'created locally'}\n"
                f"- Email draft: {draft_id or 'not requested'}"
            ),
            data={
                "title": title,
                "proposal_doc_id": doc_id,
                "proposal_doc_url": doc_url,
                "email_draft_id": draft_id,
                "recipient": recipient,
            },
            sources=[],
            next_steps=[
                "Review proposal content and update pricing/terms.",
                "Send draft email after stakeholder approval.",
            ],
            events=events,
        )
