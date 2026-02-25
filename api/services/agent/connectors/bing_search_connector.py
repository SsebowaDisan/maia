from __future__ import annotations

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

    def search_web(
        self,
        *,
        query: str,
        count: int = 8,
        mkt: str = "en-US",
        safe_search: str = "Moderate",
    ) -> dict[str, Any]:
        key = self._api_key()
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

