from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class EmailValidationConnector(BaseConnector):
    connector_id = "email_validation"

    def _provider(self) -> str:
        return str(self.settings.get("EMAIL_VALIDATION_PROVIDER") or "abstractapi").strip().lower()

    def _api_key(self) -> str:
        key = self._read_secret("EMAIL_VALIDATION_API_KEY")
        if not key:
            raise ConnectorError("EMAIL_VALIDATION_API_KEY is not configured.")
        return key

    def health_check(self) -> ConnectorHealth:
        try:
            self._api_key()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def validate(self, *, email: str) -> dict[str, Any]:
        provider = self._provider()
        key = self._api_key()
        if provider == "zerobounce":
            payload = self.request_json(
                method="GET",
                url="https://api.zerobounce.net/v2/validate",
                params={
                    "api_key": key,
                    "email": email,
                },
                timeout_seconds=20,
            )
            if not isinstance(payload, dict):
                raise ConnectorError("ZeroBounce returned invalid payload.")
            return payload

        payload = self.request_json(
            method="GET",
            url="https://emailvalidation.abstractapi.com/v1/",
            params={
                "api_key": key,
                "email": email,
            },
            timeout_seconds=20,
        )
        if not isinstance(payload, dict):
            raise ConnectorError("Abstract Email Validation returned invalid payload.")
        return payload

