from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

from api.services.agent.models import AgentAction, AgentActivityEvent, utc_now
from api.services.mailer_service import send_report_email as send_report_via_mailer
from maia.integrations.gmail_dwd import GmailDwdError

from ..models import ExecutionState, TaskPreparation
from ..side_effect_status import record_side_effect_status
from ..text_helpers import chunk_preserve_text
from .models import DeliveryRuntime


def run_delivery_send_path(
    *,
    task_prep: TaskPreparation,
    state: ExecutionState,
    runtime: DeliveryRuntime,
    report_title: str,
    report_body: str,
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    task_intelligence = task_prep.task_intelligence
    queued_delivery = activity_event_factory(
        event_type="tool_queued",
        title=runtime.title,
        detail=runtime.tool_id,
        metadata={"tool_id": runtime.tool_id, "step": runtime.step},
    )
    yield emit_event(queued_delivery)
    started_delivery = activity_event_factory(
        event_type="tool_started",
        title=runtime.title,
        detail=task_intelligence.delivery_email,
        metadata={"tool_id": runtime.tool_id, "step": runtime.step},
    )
    yield emit_event(started_delivery)
    pending_side_effect = record_side_effect_status(
        settings=state.execution_context.settings,
        action_key="send_email",
        status="pending",
        tool_id=runtime.tool_id,
        detail=f"Preparing delivery to {task_intelligence.delivery_email}",
        metadata={"step": runtime.step},
    )

    delivery_subject = (
        " ".join(str(state.execution_context.settings.get("__latest_delivery_email_subject") or "").split()).strip()
        or str(report_title or "").strip()
        or "Website Analysis Report"
    )
    delivery_body = (
        str(state.execution_context.settings.get("__latest_delivery_email_body") or "").replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
        or str(report_body or "").strip()
        or "Composing report body..."
    )
    stream_body = delivery_body
    set_recipient_event = activity_event_factory(
        event_type="email_set_to",
        title="Apply recipient",
        detail=task_intelligence.delivery_email,
        metadata={"tool_id": runtime.tool_id, "step": runtime.step},
    )
    yield emit_event(set_recipient_event)
    set_subject_event = activity_event_factory(
        event_type="email_set_subject",
        title="Apply subject",
        detail=delivery_subject,
        metadata={"tool_id": runtime.tool_id, "step": runtime.step},
    )
    yield emit_event(set_subject_event)
    typed_preview = ""
    body_chunks = chunk_preserve_text(
        stream_body,
        chunk_size=96,
        limit=max(1, (len(stream_body) // 96) + 2),
    )
    for chunk_index, body_chunk in enumerate(body_chunks, start=1):
        typed_preview += body_chunk
        typing_event = activity_event_factory(
            event_type="email_type_body",
            title="Typing email body",
            detail=body_chunk or " ",
            metadata={
                "tool_id": runtime.tool_id,
                "step": runtime.step,
                "chunk_index": chunk_index,
                "chunk_total": len(body_chunks),
                "typed_preview": typed_preview,
            },
        )
        yield emit_event(typing_event)
    set_body_event = activity_event_factory(
        event_type="email_set_body",
        title="Apply email body",
        detail=f"{len(stream_body)} characters",
        metadata={
            "tool_id": runtime.tool_id,
            "step": runtime.step,
            "typed_preview": stream_body,
        },
    )
    yield emit_event(set_body_event)
    send_prepare_event = activity_event_factory(
        event_type="email_ready_to_send",
        title="Dispatching report via Mailer Service",
        detail=task_intelligence.delivery_email,
        metadata={
            "tool_id": runtime.tool_id,
            "step": runtime.step,
            "typed_preview": stream_body,
        },
    )
    yield emit_event(send_prepare_event)

    try:
        delivery_response = send_report_via_mailer(
            to_email=task_intelligence.delivery_email,
            subject=delivery_subject,
            body_text=delivery_body or "Report requested, but no body content was generated.",
        )
        message_id = str(delivery_response.get("id") or "")
        send_summary = (
            f"Server-side Mailer Service sent report to {task_intelligence.delivery_email}. "
            f"Message ID: {message_id or 'unknown'}"
        )
        state.all_actions.append(
            AgentAction(
                tool_id=runtime.tool_id,
                action_class="execute",
                status="success",
                summary=send_summary,
                started_at=runtime.started_at,
                ended_at=utc_now().isoformat(),
                metadata={
                    "step": runtime.step,
                    "recipient": task_intelligence.delivery_email,
                    "subject": delivery_subject,
                    "message_id": message_id,
                    "external_action_key": "send_email",
                    "side_effect_status": "completed",
                },
            )
        )
        state.executed_steps.append(
            {
                "step": runtime.step,
                "tool_id": runtime.tool_id,
                "title": runtime.title,
                "status": "success",
                "summary": send_summary,
            }
        )
        sent_event = activity_event_factory(
            event_type="email_sent",
            title="Report email sent",
            detail=message_id or task_intelligence.delivery_email,
            metadata={
                "tool_id": runtime.tool_id,
                "step": runtime.step,
                "side_effect_status": "completed",
            },
        )
        yield emit_event(sent_event)
        record_side_effect_status(
            settings=state.execution_context.settings,
            action_key="send_email",
            status="completed",
            tool_id=runtime.tool_id,
            detail=send_summary,
            metadata={
                "step": runtime.step,
                "recipient": task_intelligence.delivery_email,
                "message_id": message_id,
                "pending_side_effect": pending_side_effect,
            },
        )
        completed_delivery = activity_event_factory(
            event_type="tool_completed",
            title=runtime.title,
            detail=send_summary,
            metadata={"tool_id": runtime.tool_id, "step": runtime.step},
        )
        yield emit_event(completed_delivery)
    except Exception as exc:
        mapped = exc if isinstance(exc, GmailDwdError) else RuntimeError(str(exc))
        code = str(getattr(mapped, "code", "mailer_send_failed")).strip()
        summary = f"{code}: {mapped}"
        state.all_actions.append(
            AgentAction(
                tool_id=runtime.tool_id,
                action_class="execute",
                status="failed",
                summary=summary,
                started_at=runtime.started_at,
                ended_at=utc_now().isoformat(),
                metadata={
                    "step": runtime.step,
                    "recipient": task_intelligence.delivery_email,
                    "external_action_key": "send_email",
                    "side_effect_status": "failed",
                },
            )
        )
        state.executed_steps.append(
            {
                "step": runtime.step,
                "tool_id": runtime.tool_id,
                "title": runtime.title,
                "status": "failed",
                "summary": summary,
            }
        )
        failed_delivery = activity_event_factory(
            event_type="tool_failed",
            title=runtime.title,
            detail=summary,
            metadata={
                "tool_id": runtime.tool_id,
                "step": runtime.step,
                "side_effect_status": "failed",
            },
        )
        yield emit_event(failed_delivery)
        record_side_effect_status(
            settings=state.execution_context.settings,
            action_key="send_email",
            status="failed",
            tool_id=runtime.tool_id,
            detail=summary,
            metadata={
                "step": runtime.step,
                "recipient": task_intelligence.delivery_email,
                "pending_side_effect": pending_side_effect,
            },
        )
