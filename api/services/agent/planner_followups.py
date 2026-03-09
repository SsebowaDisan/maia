from __future__ import annotations

from typing import Any

from .planner_models import PlannedStep


def build_browser_followup_steps(
    web_result_data: dict[str, Any] | None,
    *,
    max_urls: int = 3,
) -> list[PlannedStep]:
    rows = []
    if isinstance(web_result_data, dict):
        raw_rows = web_result_data.get("items")
        if isinstance(raw_rows, list):
            rows = raw_rows

    candidates: list[tuple[bool, str, str]] = []
    seen_urls: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        label = str(row.get("label") or row.get("title") or url).strip()
        if not url or not url.startswith(("http://", "https://")) or url in seen_urls:
            continue
        seen_urls.add(url)
        lowered_url = url.lower()
        is_pdf = ".pdf" in lowered_url or "application/pdf" in str(row.get("mime_type") or "").lower()
        candidates.append((is_pdf, url, label))

    # Prioritize PDF sources so live theatre includes PDF interaction when research discovers PDFs.
    candidates.sort(key=lambda item: (0 if item[0] else 1))
    followups: list[PlannedStep] = []
    for is_pdf, url, label in candidates[: max(1, int(max_urls))]:
        followups.append(
            PlannedStep(
                tool_id="browser.playwright.inspect",
                title=(
                    f"Inspect PDF source: {label[:64] or 'PDF'}"
                    if is_pdf
                    else f"Inspect source: {label[:72] or 'Website'}"
                ),
                # Keep follow-up inspections focused on the selected source URL.
                # Expanding same-domain links here can dramatically increase runtime
                # and delay final answer delivery.
                params={"url": url, "follow_same_domain_links": False},
            )
        )

    return followups
