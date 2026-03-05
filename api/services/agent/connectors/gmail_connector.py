from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth
from api.services.google.auth import GoogleAuthSession
from api.services.google.errors import GoogleServiceError
from api.services.google.gmail import GmailService


class GmailConnector(BaseConnector):
    connector_id = "gmail"

    def _session(self) -> GoogleAuthSession:
        user_id = str(self.settings.get("__agent_user_id") or self.settings.get("agent.tenant_id") or "default")
        run_id = str(self.settings.get("__agent_run_id") or "").strip() or None
        fallback = {
            "access_token": self._read_secret("GMAIL_ACCESS_TOKEN")
            or self._read_secret("GOOGLE_WORKSPACE_ACCESS_TOKEN"),
            "refresh_token": self._read_secret("GMAIL_REFRESH_TOKEN")
            or self._read_secret("GOOGLE_WORKSPACE_REFRESH_TOKEN"),
            "token_type": "Bearer",
        }
        return GoogleAuthSession(
            user_id=user_id,
            run_id=run_id,
            fallback_tokens=fallback,
            settings=self.settings,
        )

    def _access_token(self) -> str:
        token = self._session().require_access_token()
        if not token:
            raise ConnectorError(
                "GMAIL_ACCESS_TOKEN / GOOGLE OAuth token is required for Gmail connector."
            )
        return token

    def health_check(self) -> ConnectorHealth:
        try:
            token = self._access_token()
        except (ConnectorError, GoogleServiceError) as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        if not token:
            return ConnectorHealth(self.connector_id, False, "token missing")
        return ConnectorHealth(self.connector_id, True, "configured")

    def create_draft(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        sender: str = "",
    ) -> dict[str, Any]:
        service = GmailService(session=self._session())
        try:
            result = service.create_draft(
                to=to,
                subject=subject,
                body_html=body,
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {
            "draft": {
                "id": result.get("draft_id") or "",
                "message": {
                    "id": result.get("message_id") or "",
                },
            }
        }

    def add_attachment(
        self,
        *,
        draft_id: str,
        file_id: str | None = None,
        local_path: str | None = None,
    ) -> dict[str, Any]:
        service = GmailService(session=self._session())
        try:
            return service.add_attachment(draft_id=draft_id, file_id=file_id, local_path=local_path)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc

    def send_draft(self, *, draft_id: str) -> dict[str, Any]:
        service = GmailService(session=self._session())
        try:
            result = service.send_draft(draft_id=draft_id)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {"id": result.get("message_id") or ""}

    def send_message(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        sender: str = "",
    ) -> dict[str, Any]:
        service = GmailService(session=self._session())
        try:
            result = service.send_message(
                to=to,
                subject=subject,
                body_html=body,
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {
            "id": result.get("message_id") or "",
            "threadId": result.get("thread_id") or "",
        }

    def send_message_with_attachments(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        attachments: list[dict[str, str]],
        sender: str = "",
    ) -> dict[str, Any]:
        _ = sender
        service = GmailService(session=self._session())
        try:
            result = service.send_message_with_attachments(
                to=to,
                subject=subject,
                body_html=body,
                attachments=attachments,
            )
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {
            "id": result.get("message_id") or "",
            "threadId": result.get("thread_id") or "",
            "attachments_count": int(result.get("attachments_count") or 0),
        }

    def list_messages(self, *, query: str = "", max_results: int = 20) -> dict[str, Any]:
        service = GmailService(session=self._session())
        try:
            result = service.search_messages(query=query, max_results=max_results)
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        return {"messages": result.get("messages") or []}

    # Backward-compatible helpers retained for any external callers.
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
        }

    def _raw_message(self, *, sender: str, to: str, subject: str, body: str) -> str:
        _ = sender  # Sender is controlled by Gmail account for OAuth user.
        raise ConnectorError("Legacy raw message helper is deprecated for GmailConnector.")

    def _legacy_access_token(self) -> str:
        token = self._read_secret("GMAIL_ACCESS_TOKEN") or self._read_secret(
            "GOOGLE_WORKSPACE_ACCESS_TOKEN"
        )
        if not token:
            raise ConnectorError("GMAIL_ACCESS_TOKEN (or GOOGLE_WORKSPACE_ACCESS_TOKEN) is required.")
        return token
