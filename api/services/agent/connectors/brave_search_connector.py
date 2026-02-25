from __future__ import annotations

import os
from typing import Any

from api.services.search.brave_search import BraveSearchService
from api.services.search.errors import BraveSearchError

from .base import BaseConnector, ConnectorError, ConnectorHealth


class BraveSearchConnector(BaseConnector):
    connector_id = "brave_search"

    def _api_key(self) -> str:
        env_key = str(os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()
        if env_key:
            return env_key
        stored_key = str(self.settings.get("BRAVE_SEARCH_API_KEY") or "").strip()
        if stored_key:
            return stored_key
        raise ConnectorError("BRAVE_SEARCH_API_KEY is not configured.")

    def health_check(self) -> ConnectorHealth:
        try:
            self._api_key()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def web_search(
        self,
        *,
        query: str,
        count: int = 10,
        offset: int = 0,
        country: str = "BE",
        safesearch: str = "moderate",
    ) -> dict[str, Any]:
        try:
            service = BraveSearchService(api_key=self._api_key())
            return service.web_search(
                query=query,
                count=count,
                offset=offset,
                country=country,
                safesearch=safesearch,
            )
        except BraveSearchError as exc:
            raise ConnectorError(str(exc)) from exc

    def site_search(
        self,
        *,
        domain: str,
        query: str,
        count: int = 10,
        offset: int = 0,
        country: str = "BE",
        safesearch: str = "moderate",
    ) -> dict[str, Any]:
        try:
            service = BraveSearchService(api_key=self._api_key())
            return service.site_search(
                domain=domain,
                query=query,
                count=count,
                offset=offset,
                country=country,
                safesearch=safesearch,
            )
        except BraveSearchError as exc:
            raise ConnectorError(str(exc)) from exc
