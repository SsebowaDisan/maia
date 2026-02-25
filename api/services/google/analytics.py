from __future__ import annotations

from typing import Any

from api.services.google.auth import GoogleAuthSession
from api.services.google.events import emit_google_event


class GoogleAnalyticsService:
    def __init__(self, *, session: GoogleAuthSession) -> None:
        self.session = session

    def run_report(
        self,
        *,
        property_id: str,
        date_range: dict[str, str] | list[dict[str, str]],
        metrics: list[str],
        dimensions: list[str],
        filters: dict[str, Any] | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        date_ranges: list[dict[str, str]]
        if isinstance(date_range, list):
            date_ranges = date_range
        else:
            date_ranges = [date_range]
        payload: dict[str, Any] = {
            "dateRanges": date_ranges,
            "metrics": [{"name": item} for item in metrics],
            "dimensions": [{"name": item} for item in dimensions],
            "limit": str(max(1, min(int(limit), 5000))),
        }
        if filters:
            payload["dimensionFilter"] = filters

        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="analytics.report_started",
            message="Running GA4 report",
            data={"property_id": property_id, "metrics": metrics, "dimensions": dimensions},
        )
        raw = self.session.request_json(
            method="POST",
            url=f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
            payload=payload,
            timeout=60,
        )
        rows = raw.get("rows") if isinstance(raw, dict) else []
        if not isinstance(rows, list):
            rows = []
        summary = {
            "row_count": len(rows),
            "metric_headers": [
                str(item.get("name") or "")
                for item in (raw.get("metricHeaders") or [])
                if isinstance(item, dict)
            ],
            "dimension_headers": [
                str(item.get("name") or "")
                for item in (raw.get("dimensionHeaders") or [])
                if isinstance(item, dict)
            ],
        }
        emit_google_event(
            user_id=self.session.user_id,
            run_id=self.session.run_id,
            event_type="analytics.report_completed",
            message="GA4 report completed",
            data={"property_id": property_id, "row_count": len(rows)},
        )
        return {"rows": rows, "summary": summary, "raw": raw}

