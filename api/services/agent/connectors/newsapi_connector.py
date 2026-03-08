from __future__ import annotations

import time
from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth

_ENDPOINT = "https://newsapi.org/v2/everything"
_MAX_RESULTS_CAP = 20
_NEWS_SIGNALS = frozenset(
    [
        "news", "latest", "recent", "today", "yesterday", "this week",
        "announcement", "press release", "report", "update", "breaking",
        "2024", "2025", "2026", "event", "launch", "release", "develop",
    ]
)


def _has_news_signal(query: str) -> bool:
    lower = query.lower()
    return any(sig in lower for sig in _NEWS_SIGNALS)


def _normalize_article(article: dict[str, Any]) -> dict[str, Any] | None:
    url = str(article.get("url") or "").strip()
    if not url or not url.startswith("http"):
        return None
    title = str(article.get("title") or "").strip()
    if not title or title.lower() == "[removed]":
        return None
    description = str(article.get("description") or article.get("content") or "").strip()[:320]
    if description.lower().startswith("[removed]"):
        description = ""
    return {
        "url": url,
        "title": title,
        "description": description,
        "source": "newsapi",
        "published_at": str(article.get("publishedAt") or "").strip(),
    }


class NewsAPIConnector(BaseConnector):
    """Search NewsAPI for recent news articles. Requires NEWSAPI_API_KEY."""

    connector_id = "newsapi"

    def _api_key(self) -> str:
        key = self._read_secret("NEWSAPI_API_KEY")
        if not key:
            raise ConnectorError("NEWSAPI_API_KEY is not configured.")
        return key

    def health_check(self) -> ConnectorHealth:
        try:
            self._api_key()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    @staticmethod
    def _retryable_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(code in text for code in (" 429", " 500", " 502", " 503", " 504", "timed out", "timeout", "temporar"))

    def search(
        self,
        *,
        query: str,
        count: int = 8,
        language: str = "en",
        sort_by: str = "relevancy",
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
    ) -> list[dict[str, Any]]:
        key = self._api_key()
        count = max(1, min(int(count), _MAX_RESULTS_CAP))
        attempts = max(0, int(max_retries))
        for attempt in range(attempts + 1):
            try:
                payload = self.request_json(
                    method="GET",
                    url=_ENDPOINT,
                    headers={"X-Api-Key": key},
                    params={
                        "q": query,
                        "pageSize": count,
                        "language": language,
                        "sortBy": sort_by,
                    },
                    timeout_seconds=20,
                )
                if not isinstance(payload, dict):
                    return []
                articles = payload.get("articles")
                if not isinstance(articles, list):
                    return []
                results: list[dict[str, Any]] = []
                for article in articles[:count]:
                    if not isinstance(article, dict):
                        continue
                    normalized = _normalize_article(article)
                    if normalized:
                        results.append(normalized)
                return results
            except ConnectorError as exc:
                if attempt >= attempts or not self._retryable_error(exc):
                    raise
                time.sleep(max(0.05, float(backoff_seconds)) * float(attempt + 1))
        return []

    def search_web(
        self,
        *,
        query: str,
        count: int = 8,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Unified interface matching other connectors — returns {results: [...]}."""
        results = self.search(query=query, count=count)
        return {"results": results}
