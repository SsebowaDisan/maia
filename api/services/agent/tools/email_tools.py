from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)
from api.services.agent.tools.business_workflow_helpers import email_from_text
from api.services.agent.tools.theater_cursor import with_scene


def _email_scene_payload(
    *,
    lane: str,
    payload: dict[str, Any] | None = None,
    primary_index: int = 1,
    secondary_index: int = 1,
) -> dict[str, Any]:
    return with_scene(
        payload or {},
        scene_surface="email",
        lane=lane,
        primary_index=max(1, int(primary_index)),
        secondary_index=max(1, int(secondary_index)),
    )


class EmailDraftTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="email.draft",
        action_class="draft",
        risk_level="low",
        required_permissions=["email.draft"],
        execution_policy="auto_execute",
        description="Draft a professional business email.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        recipient = str(
            params.get("to")
            or context.settings.get("__latest_delivery_email_to")
            or email_from_text(prompt)
            or ""
        ).strip()
        if not recipient:
            raise ToolExecutionError("Email recipient is required (`to`).")
        subject = str(params.get("subject") or "Update")
        objective = str(params.get("objective") or prompt).strip() or "Share update"

        content = (
            f"To: {recipient}\n"
            f"Subject: {subject}\n\n"
            "Hello,\n\n"
            f"{objective}\n\n"
            "Key points:\n"
            "- Current status and measurable progress\n"
            "- Risks and dependencies\n"
            "- Next action with owner and timeline\n\n"
            "Regards,\nMaia Agent"
        )
        return ToolExecutionResult(
            summary=f"Drafted email to {recipient}.",
            content=content,
            data={"to": recipient, "subject": subject},
            sources=[],
            next_steps=["Review tone and recipients before sending."],
            events=[
                ToolTraceEvent(
                    event_type="email_draft_create",
                    title="Create draft envelope",
                    detail="Initialized email draft structure",
                    data=_email_scene_payload(
                        lane="email-draft-create",
                        payload={"to": recipient, "subject": subject},
                    ),
                ),
                ToolTraceEvent(
                    event_type="email_set_to",
                    title="Set recipients",
                    detail=f"Recipient: {recipient}",
                    data=_email_scene_payload(
                        lane="email-set-to",
                        payload={"to": recipient},
                    ),
                ),
                ToolTraceEvent(
                    event_type="email_set_subject",
                    title="Set subject",
                    detail=subject,
                    data=_email_scene_payload(
                        lane="email-set-subject",
                        payload={"subject": subject},
                    ),
                ),
                ToolTraceEvent(
                    event_type="email_set_body",
                    title="Draft body content",
                    detail="Body generated from task objective",
                    data=_email_scene_payload(
                        lane="email-set-body",
                        payload={"body_length": len(content)},
                    ),
                ),
                ToolTraceEvent(
                    event_type="email_ready_to_send",
                    title="Draft ready for send",
                    detail="Draft prepared with recipient and subject",
                    data=_email_scene_payload(
                        lane="email-ready",
                        payload={"to": recipient, "subject": subject},
                    ),
                ),
            ],
        )


class EmailSendTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="email.send",
        action_class="execute",
        risk_level="high",
        required_permissions=["email.send"],
        execution_policy="confirm_before_execute",
        description="Send an email through configured SMTP provider.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        host = str(context.settings.get("agent.smtp_host") or os.getenv("AGENT_SMTP_HOST") or "").strip()
        port = int(context.settings.get("agent.smtp_port") or os.getenv("AGENT_SMTP_PORT") or 587)
        username = str(
            context.settings.get("agent.smtp_username") or os.getenv("AGENT_SMTP_USERNAME") or ""
        ).strip()
        password = str(
            context.settings.get("agent.smtp_password") or os.getenv("AGENT_SMTP_PASSWORD") or ""
        ).strip()
        sender = str(params.get("from") or username).strip()
        recipient = str(params.get("to") or "").strip()
        subject = str(params.get("subject") or "Company update").strip()
        body = str(params.get("body") or prompt).strip()

        if not recipient:
            raise ToolExecutionError("Email recipient is required.")

        if not host or not username or not password:
            return ToolExecutionResult(
                summary="SMTP is not configured. Email delivery skipped.",
                content=(
                    "SMTP credentials are missing. Configure `agent.smtp_host`, "
                    "`agent.smtp_port`, `agent.smtp_username`, and `agent.smtp_password`."
                ),
                data={"status": "skipped"},
                sources=[],
                next_steps=["Configure SMTP settings, then retry send."],
                events=[
                    ToolTraceEvent(
                        event_type="approval_required",
                        title="SMTP credentials missing",
                        detail="Configure SMTP settings before sending email.",
                        data=_email_scene_payload(
                            lane="email-config-missing",
                            payload={"to": recipient, "subject": subject},
                        ),
                    )
                ],
            )

        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(host=host, port=port, timeout=25) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)

        return ToolExecutionResult(
            summary=f"Email sent to {recipient}.",
            content=f"Email delivered to {recipient} with subject: {subject}",
            data={"status": "sent", "to": recipient, "subject": subject},
            sources=[],
            next_steps=["Capture recipient response and update CRM/worklog."],
            events=[
                ToolTraceEvent(
                    event_type="email_set_to",
                    title="Confirm recipient",
                    detail=f"Recipient: {recipient}",
                    data=_email_scene_payload(
                        lane="email-confirm-to",
                        payload={"to": recipient},
                    ),
                ),
                ToolTraceEvent(
                    event_type="email_set_subject",
                    title="Confirm subject",
                    detail=subject,
                    data=_email_scene_payload(
                        lane="email-confirm-subject",
                        payload={"subject": subject},
                    ),
                ),
                ToolTraceEvent(
                    event_type="email_sent",
                    title="Email dispatched",
                    detail=f"SMTP delivery completed for {recipient}",
                    data=_email_scene_payload(
                        lane="email-sent",
                        payload={"to": recipient, "subject": subject},
                    ),
                ),
            ],
        )
