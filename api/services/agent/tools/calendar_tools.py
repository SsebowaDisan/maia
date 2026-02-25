from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)


def _default_start_end() -> tuple[str, str]:
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    end = start + timedelta(minutes=30)
    return start.isoformat(), end.isoformat()


class CalendarCreateEventTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="calendar.create_event",
        action_class="execute",
        risk_level="high",
        required_permissions=["calendar.write"],
        execution_policy="confirm_before_execute",
        description="Create Google Calendar events for meetings and reminders.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        summary = str(params.get("summary") or "Company follow-up").strip()
        description = str(params.get("description") or prompt).strip()
        default_start, default_end = _default_start_end()
        start_iso = str(params.get("start_iso") or default_start).strip()
        end_iso = str(params.get("end_iso") or default_end).strip()
        calendar_id = str(params.get("calendar_id") or "primary").strip()
        attendees = params.get("attendees")
        attendee_emails = [str(item).strip() for item in attendees] if isinstance(attendees, list) else []

        connector = get_connector_registry().build("google_calendar", settings=context.settings)
        event = connector.create_event(
            summary=summary,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description,
            attendees=attendee_emails,
            calendar_id=calendar_id,
        )
        html_link = str(event.get("htmlLink") or "")
        event_id = str(event.get("id") or "")

        return ToolExecutionResult(
            summary=f"Calendar event created: {summary}.",
            content=(
                f"Created calendar event.\n"
                f"- Summary: {summary}\n"
                f"- Start: {start_iso}\n"
                f"- End: {end_iso}\n"
                f"- Event ID: {event_id or 'unknown'}\n"
                f"- Link: {html_link or 'not available'}"
            ),
            data={"event_id": event_id, "html_link": html_link, "summary": summary},
            sources=[],
            next_steps=["Share calendar invite with participants and attach agenda document."],
            events=[
                ToolTraceEvent(
                    event_type="tool_progress",
                    title="Create calendar event",
                    detail=summary,
                    data={"summary": summary},
                ),
                ToolTraceEvent(
                    event_type="tool_completed",
                    title="Calendar event created",
                    detail=event_id or summary,
                    data={"event_id": event_id, "link": html_link},
                ),
            ],
        )

