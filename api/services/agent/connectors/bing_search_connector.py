from __future__ import annotations

import time
from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class BingSearchConnector(BaseConnector):
    connector_id = "bing_search"

    def _api_key(self) -> str:
        key = self._read_secret("AZURE_BING_API_KEY") or self._read_secret("BING_SEARCH_API_KEY")
        if not key:
            raise ConnectorError("AZURE_BING_API_KEY (or BING_SEARCH_API_KEY) is not configured.")
        return key

    def _endpoint(self) -> str:
        endpoint = self._read_secret("BING_SEARCH_ENDPOINT")
        if endpoint:
            return endpoint.rstrip("/")
        return "https://api.bing.microsoft.com/v7.0/search"

    def health_check(self) -> ConnectorHealth:
        try:
            self._api_key()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    @staticmethod
    def _retryable_error(exc: Exception) -> bool:
        text = str(exc).lower()
        if any(code in text for code in (" 429", " 500", " 502", " 503", " 504")):
            return True
        if "timed out" in text or "timeout" in text:
            return True
        if "temporar" in text:
            return True
        return False

    def search_web(
        self,
        *,
        query: str,
        count: int = 8,
        mkt: str = "en-US",
        safe_search: str = "Moderate",
        max_retries: int = 2,
        backoff_seconds: float = 0.45,
    ) -> dict[str, Any]:
        key = self._api_key()
        attempts = max(0, int(max_retries))
        for attempt in range(attempts + 1):
            try:
                payload = self.request_json(
                    method="GET",
                    url=self._endpoint(),
                    headers={"Ocp-Apim-Subscription-Key": key},
                    params={
                        "q": query,
                        "count": max(1, min(int(count), 50)),
                        "mkt": mkt,
                        "safeSearch": safe_search,
                        "textDecorations": False,
                        "textFormat": "Raw",
                    },
                    timeout_seconds=25,
                )
                if not isinstance(payload, dict):
                    raise ConnectorError("Bing Search API returned invalid response payload.")
                return payload
            except ConnectorError as exc:
                if attempt >= attempts or not self._retryable_error(exc):
                    raise
                time.sleep(max(0.05, float(backoff_seconds)) * float(attempt + 1))
        raise ConnectorError("Bing Search API request failed after retries.")
