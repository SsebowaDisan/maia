from __future__ import annotations

from dataclasses import dataclass
import os
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ConnectorHealth:
    connector_id: str
    ok: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "ok": self.ok,
            "message": self.message,
        }


class ConnectorError(RuntimeError):
    pass


class BaseConnector:
    connector_id = "base"

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or {}

    def _read_secret(self, env_name: str) -> str:
        return str(self.settings.get(env_name) or os.getenv(env_name, "")).strip()

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            connector_id=self.connector_id,
            ok=True,
            message="connector loaded",
        )

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 25,
    ) -> Any:
        full_url = url
        if params:
            query = urlencode({key: value for key, value in params.items() if value is not None})
            full_url = f"{url}?{query}" if query else url
        body = None
        final_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            final_headers.setdefault("Content-Type", "application/json")
        request = Request(full_url, data=body, method=method.upper(), headers=final_headers)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                data = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ConnectorError(
                f"{self.connector_id} request failed ({exc.code}): {detail[:240]}"
            ) from exc
        except Exception as exc:
            raise ConnectorError(f"{self.connector_id} request error: {exc}") from exc

        if not data:
            return {}
        try:
            return json.loads(data.decode("utf-8"))
        except Exception as exc:
            raise ConnectorError(f"{self.connector_id} invalid JSON response: {exc}") from exc
