from __future__ import annotations

from typing import Any

from api.services.google.auth import GoogleAuthSession
from api.services.google.errors import GoogleServiceError
from api.services.google.oauth_scopes import connector_required_scopes

from .base import BaseConnector, ConnectorError, ConnectorHealth


class GoogleCalendarConnector(BaseConnector):
    connector_id = "google_calendar"

    def _session(self) -> GoogleAuthSession:
        user_id = str(self.settings.get("__agent_user_id") or self.settings.get("agent.tenant_id") or "default")
        run_id = str(self.settings.get("__agent_run_id") or "").strip() or None
        fallback = {
            "access_token": self._read_secret("GOOGLE_CALENDAR_ACCESS_TOKEN")
            or self._read_secret("GOOGLE_WORKSPACE_ACCESS_TOKEN"),
            "refresh_token": self._read_secret("GOOGLE_CALENDAR_REFRESH_TOKEN")
            or self._read_secret("GOOGLE_WORKSPACE_REFRESH_TOKEN"),
            "token_type": "Bearer",
        }
        return GoogleAuthSession(
            user_id=user_id,
            run_id=run_id,
            fallback_tokens=fallback,
            settings=self.settings,
        )

    def _authorized_session(self) -> GoogleAuthSession:
        session = self._session()
        session.require_scopes(
            connector_required_scopes(self.connector_id),
            reason="Google Calendar access",
        )
        return session

    def _access_token(self) -> str:
        token = self._authorized_session().require_access_token()
        if not token:
            raise ConnectorError(
                "GOOGLE_CALENDAR_ACCESS_TOKEN (or GOOGLE_WORKSPACE_ACCESS_TOKEN) is required."
            )
        return token

    def health_check(self) -> ConnectorHealth:
        try:
            self._access_token()
        except (ConnectorError, GoogleServiceError) as exc:
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
        session = self._authorized_session()
        payload = session.request_json(
            method="POST",
            url=f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            payload={
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
                "attendees": attendee_rows,
            },
            timeout=25,
        )
        if not isinstance(payload, dict):
            raise ConnectorError("Google Calendar create event returned invalid payload.")
        return payload
