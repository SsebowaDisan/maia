from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote_plus

from .base import BaseConnector, ConnectorError, ConnectorHealth

_ENDPOINT = "https://www.reddit.com/search.json"
_MAX_RESULTS_CAP = 15
_SENTIMENT_SIGNALS = frozenset(
    [
        "opinion", "review", "experience", "community", "reddit", "forum",
        "discussion", "people think", "what do", "recommendations", "advice",
        "thoughts on", "sentiment", "feedback", "users say", "customers say",
    ]
)


def _has_sentiment_signal(query: str) -> bool:
    lower = query.lower()
    return any(sig in lower for sig in _SENTIMENT_SIGNALS)


def _normalize_post(post_data: dict[str, Any]) -> dict[str, Any] | None:
    permalink = str(post_data.get("permalink") or "").strip()
    if not permalink:
        return None
    url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
    title = str(post_data.get("title") or "").strip()
    if not title:
        return None
    selftext = str(post_data.get("selftext") or "").strip()
    description = selftext[:300] if len(selftext) > 300 else selftext
    subreddit = str(post_data.get("subreddit_name_prefixed") or "").strip()
    if subreddit:
        description = f"[{subreddit}] {description}".strip()
    return {
        "url": url,
        "title": title,
        "description": description,
        "source": "reddit",
        "score": int(post_data.get("score") or 0),
    }


class RedditConnector(BaseConnector):
    """Search Reddit for community discussions. Free, no API key required."""

    connector_id = "reddit"

    def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(self.connector_id, True, "no credentials required")

    @staticmethod
    def _retryable_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(code in text for code in (" 429", " 500", " 502", " 503", " 504", "timed out", "timeout", "temporar"))

    def search(
        self,
        *,
        query: str,
        count: int = 8,
        sort: str = "relevance",
        time_filter: str = "year",
        max_retries: int = 2,
        backoff_seconds: float = 0.6,
    ) -> list[dict[str, Any]]:
        count = max(1, min(int(count), _MAX_RESULTS_CAP))
        attempts = max(0, int(max_retries))
        encoded = quote_plus(query)
        url = f"{_ENDPOINT}?q={encoded}&sort={sort}&t={time_filter}&limit={count}&type=link"
        for attempt in range(attempts + 1):
            try:
                payload = self.request_json(
                    method="GET",
                    url=url,
                    headers={"User-Agent": "MaiaResearchBot/1.0 (business research assistant)"},
                    timeout_seconds=18,
                )
                if not isinstance(payload, dict):
                    return []
                data = payload.get("data") or {}
                children = (data.get("children") or []) if isinstance(data, dict) else []
                results: list[dict[str, Any]] = []
                for child in children[:count]:
                    if not isinstance(child, dict):
                        continue
                    post_data = child.get("data") or {}
                    if not isinstance(post_data, dict):
                        continue
                    normalized = _normalize_post(post_data)
                    if normalized:
                        results.append(normalized)
                return results
            except ConnectorError as exc:
                if attempt >= attempts or not self._retryable_error(exc):
                    return []
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
