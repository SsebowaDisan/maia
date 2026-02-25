from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class SlackConnector(BaseConnector):
    connector_id = "slack"

    def _token(self) -> str:
        token = self._read_secret("SLACK_BOT_TOKEN")
        if not token:
            raise ConnectorError("SLACK_BOT_TOKEN is not configured.")
        return token

    def health_check(self) -> ConnectorHealth:
        try:
            token = self._token()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        if not token.startswith("xoxb-"):
            return ConnectorHealth(self.connector_id, False, "Token format is invalid.")
        return ConnectorHealth(self.connector_id, True, "configured")

    def post_message(self, channel: str, text: str) -> dict[str, Any]:
        token = self._token()
        response = self.request_json(
            method="POST",
            url="https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            payload={"channel": channel, "text": text},
        )
        if not response.get("ok"):
            raise ConnectorError(f"Slack API error: {response.get('error', 'unknown_error')}")
        return response
