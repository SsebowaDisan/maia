from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth
from api.services.google.analytics import GoogleAnalyticsService
from api.services.google.auth import GoogleAuthSession
from api.services.google.errors import GoogleServiceError
from api.services.google.oauth_scopes import connector_required_scopes


class GoogleAnalyticsConnector(BaseConnector):
    connector_id = "google_analytics"

    def _access_token(self) -> str:
        token = self._session().require_access_token()
        if not token:
            raise ConnectorError(
                "GOOGLE_ANALYTICS_ACCESS_TOKEN (or GOOGLE_WORKSPACE_ACCESS_TOKEN) is required."
            )
        return token

    def _property_id(self, payload_property_id: str | None = None) -> str:
        property_id = str(
            payload_property_id
            or self.settings.get("agent.google_analytics_property_id")
            or self.settings.get("GOOGLE_ANALYTICS_PROPERTY_ID")
            or self._read_secret("GOOGLE_ANALYTICS_PROPERTY_ID")
        ).strip()
        if not property_id:
            raise ConnectorError(
                "GA4 property ID is not configured. "
                "Set it in Settings → Integrations → Google Analytics Property ID."
            )
        return property_id

    def _session(self) -> GoogleAuthSession:
        user_id = str(self.settings.get("__agent_user_id") or self.settings.get("agent.tenant_id") or "default")
        run_id = str(self.settings.get("__agent_run_id") or "").strip() or None
        fallback = {
            "access_token": self._read_secret("GOOGLE_ANALYTICS_ACCESS_TOKEN")
            or self._read_secret("GOOGLE_WORKSPACE_ACCESS_TOKEN"),
            "refresh_token": self._read_secret("GOOGLE_ANALYTICS_REFRESH_TOKEN")
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
            reason="Google Analytics access",
        )
        return session

    def health_check(self) -> ConnectorHealth:
        try:
            self._authorized_session().require_access_token()
            self._property_id()
        except (ConnectorError, GoogleServiceError) as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def run_report(
        self,
        *,
        property_id: str | None = None,
        date_ranges: list[dict[str, str]] | None = None,
        dimensions: list[str] | None = None,
        metrics: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        resolved_property_id = self._property_id(property_id)
        service = GoogleAnalyticsService(session=self._authorized_session())
        try:
            response = service.run_report(
                property_id=resolved_property_id,
                date_range=date_ranges or [{"startDate": "30daysAgo", "endDate": "today"}],
                dimensions=(dimensions or ["sessionDefaultChannelGroup"]),
                metrics=(metrics or ["sessions", "totalUsers", "conversions"]),
                limit=limit,
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        raw = response.get("raw")
        if not isinstance(raw, dict):
            raise ConnectorError("GA4 runReport returned invalid payload.")
        return raw
