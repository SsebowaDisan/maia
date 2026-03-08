from __future__ import annotations

import time
from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth

_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"
_MAX_RESULTS_CAP = 20
_FINANCIAL_SIGNALS = frozenset(
    [
        "sec", "edgar", "filing", "annual report", "10-k", "10k", "earnings",
        "revenue", "profit", "income", "financial", "quarterly", "investor",
        "stock", "shares", "company", "corporation", "ipo", "balance sheet",
        "cash flow", "dividend", "acquisition", "merger", "sec filing",
    ]
)


def _has_financial_signal(query: str) -> bool:
    lower = query.lower()
    return any(sig in lower for sig in _FINANCIAL_SIGNALS)


def _normalize_hit(hit: dict[str, Any]) -> dict[str, Any] | None:
    display_names = hit.get("display_names") or hit.get("entity_name") or ""
    entity = display_names[0] if isinstance(display_names, list) and display_names else str(display_names)
    form_type = str(hit.get("form_type") or "").strip()
    file_date = str(hit.get("file_date") or "").strip()
    entity_name = str(entity or "").strip()
    accession = str(hit.get("_id") or hit.get("accession_no") or "").strip().replace("-", "")
    if not accession:
        return None
    url = f"https://www.sec.gov/Archives/edgar/data/{accession[:10]}/{accession}.htm"
    title_parts = [p for p in [entity_name, form_type, file_date] if p]
    title = " — ".join(title_parts) if title_parts else f"SEC Filing {accession}"
    description = str(hit.get("period_of_report") or hit.get("description") or "").strip()[:300]
    return {
        "url": url,
        "title": title,
        "description": description,
        "source": "sec_edgar",
    }


class SecEdgarConnector(BaseConnector):
    """Search SEC EDGAR full-text search index. Free, no API key required."""

    connector_id = "sec_edgar"

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
        attempts = max(0, int(max_retries))
        for attempt in range(attempts + 1):
            try:
                payload = self.request_json(
                    method="GET",
                    url=_ENDPOINT,
                    params={
                        "q": query,
                        "dateRange": "custom",
                        "startdt": "2015-01-01",
                        "hits.hits.total.value": count,
                        "hits.hits._source": "period_of_report,entity_name,form_type,file_date,accession_no",
                    },
                    timeout_seconds=20,
                )
                if not isinstance(payload, dict):
                    return []
                hits_obj = payload.get("hits") or {}
                hits = (hits_obj.get("hits") or []) if isinstance(hits_obj, dict) else []
                results: list[dict[str, Any]] = []
                for hit in hits[:count]:
                    source = hit.get("_source") or hit
                    if not isinstance(source, dict):
                        continue
                    normalized = _normalize_hit(source)
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
