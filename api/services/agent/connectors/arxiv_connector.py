from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

from .base import BaseConnector, ConnectorError, ConnectorHealth

_ARXIV_NS = "http://www.w3.org/2005/Atom"
_MAX_RESULTS_CAP = 25
_ENDPOINT = "https://export.arxiv.org/api/query"
_ACADEMIC_SIGNALS = frozenset(
    [
        "research", "paper", "study", "journal", "arxiv", "academic",
        "machine learning", "algorithm", "model", "neural", "llm",
        "science", "theory", "analysis", "survey", "review",
    ]
)


def _has_academic_signal(query: str) -> bool:
    lower = query.lower()
    return any(sig in lower for sig in _ACADEMIC_SIGNALS)


def _parse_arxiv_xml(raw: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return []
    ns = {"atom": _ARXIV_NS}
    results: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        id_el = entry.find("atom:id", ns)
        title = " ".join((title_el.text or "").split()) if title_el is not None else ""
        summary = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
        raw_id = (id_el.text or "").strip() if id_el is not None else ""
        # Normalize to abs URL
        url = raw_id if raw_id.startswith("http") else f"https://arxiv.org/abs/{raw_id.rsplit('/', 1)[-1]}"
        if not url or not title:
            continue
        description = summary[:360] if len(summary) > 360 else summary
        results.append(
            {
                "url": url,
                "title": title,
                "description": description,
                "source": "arxiv",
            }
        )
    return results


class ArXivConnector(BaseConnector):
    """Search ArXiv for academic papers. Free, no API key required."""

    connector_id = "arxiv"

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
        max_retries: int = 2,
        backoff_seconds: float = 0.5,
    ) -> list[dict[str, Any]]:
        count = max(1, min(int(count), _MAX_RESULTS_CAP))
        encoded = quote_plus(query)
        url = f"{_ENDPOINT}?search_query=all:{encoded}&start=0&max_results={count}"
        attempts = max(0, int(max_retries))
        for attempt in range(attempts + 1):
            try:
                from urllib.request import urlopen
                from urllib.error import HTTPError
                try:
                    with urlopen(url, timeout=20) as resp:
                        raw = resp.read()
                except HTTPError as exc:
                    raise ConnectorError(f"arxiv request failed ({exc.code})") from exc
                return _parse_arxiv_xml(raw)
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
