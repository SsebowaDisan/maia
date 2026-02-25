from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class GoogleCalendarConnector(BaseConnector):
    connector_id = "google_calendar"

    def _access_token(self) -> str:
        token = self._read_secret("GOOGLE_CALENDAR_ACCESS_TOKEN") or self._read_secret(
            "GOOGLE_WORKSPACE_ACCESS_TOKEN"
        )
        if not token:
            raise ConnectorError(
                "GOOGLE_CALENDAR_ACCESS_TOKEN (or GOOGLE_WORKSPACE_ACCESS_TOKEN) is required."
            )
        return token

    def health_check(self) -> ConnectorHealth:
        try:
            self._access_token()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def create_event(
        self,
        *,
        summary: str,
        start_iso: str,
        end_iso: str,
        description: str = "",
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        attendee_rows = [{"email": email} for email in (attendees or []) if email]
        payload = self.request_json(
            method="POST",
            url=f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
            },
            payload={
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
                "attendees": attendee_rows,
            },
            timeout_seconds=25,
        )
        if not isinstance(payload, dict):
            raise ConnectorError("Google Calendar create event returned invalid payload.")
        return payload

