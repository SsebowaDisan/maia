from __future__ import annotations

from pathlib import Path
from typing import Any

from api.services.agent.llm_runtime import has_openai_credentials

from .contact_channels import (
    collect_contact_channels as _collect_contact_channels,
    cursor_payload,
    normalize_url,
    page_title,
    safe_text,
)
from .contact_form_locator import find_best_form
from .contact_navigation import (
    capture_navigation_snapshot,
    collect_navigation_candidates,
    perform_exploratory_scroll,
    rank_navigation_candidates as _rank_navigation_candidates,
)


def collect_contact_channels(page: Any) -> dict[str, list[str]]:
    return _collect_contact_channels(page)


def rank_navigation_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_hops: int,
) -> list[int]:
    if not candidates:
        return []
    if not has_openai_credentials():
        return list(range(min(len(candidates), max(1, int(max_hops)))))
    return _rank_navigation_candidates(candidates, max_hops=max_hops)


def locate_contact_form_with_discovery(
    page: Any,
    *,
    wait_ms: int,
    timeout_ms: int = 12000,
    max_hops: int = 5,
    output_dir: Path | None = None,
    stamp_prefix: str = "",
) -> tuple[Any | None, bool, list[dict[str, Any]]]:
    traces: list[dict[str, Any]] = []
    channels = collect_contact_channels(page)
    traces.append(
        {
            "event_type": "browser_extract",
            "title": "Extract contact channels",
            "detail": (
                f"emails={len(channels.get('emails') or [])}, "
                f"phones={len(channels.get('phones') or [])}"
            ),
            "data": {
                "url": normalize_url(str(page.url or "")),
                "title": page_title(page),
                "contact_channels": channels,
                **cursor_payload(page),
            },
            "snapshot_ref": None,
        }
    )

    form = find_best_form(page)
    if form is not None:
        return form, False, traces

    scroll_event = perform_exploratory_scroll(
        page=page,
        wait_ms=wait_ms,
        reason="Scroll current page while searching for inquiry form",
    )
    if scroll_event is not None:
        traces.append(scroll_event)
        form = find_best_form(page)
        if form is not None:
            return form, False, traces

    candidates = collect_navigation_candidates(page, max_items=max(max_hops * 8, 16))
    ranked_indexes = rank_navigation_candidates(candidates, max_hops=max_hops)
    if not ranked_indexes:
        return None, False, traces

    visited: set[str] = set()
    for rank, candidate_index in enumerate(ranked_indexes, start=1):
        candidate = candidates[candidate_index]
        target_url = normalize_url(candidate.get("url"))
        if not target_url or target_url in visited:
            continue
        visited.add(target_url)
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=max(4000, int(timeout_ms)))
            page.wait_for_timeout(max(250, int(wait_ms)))
        except Exception:
            continue
        snapshot_ref = capture_navigation_snapshot(
            page=page,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
            hop_index=rank,
        )
        traces.append(
            {
                "event_type": "browser_navigate",
                "title": "Navigate to likely inquiry page",
                "detail": safe_text(candidate.get("label") or target_url, max_len=200),
                "data": {
                    "url": normalize_url(str(page.url or "")) or target_url,
                    "title": page_title(page),
                    "candidate_rank": rank,
                    "candidate_index": candidate_index,
                    "candidate_url": target_url,
                    **cursor_payload(page),
                },
                "snapshot_ref": snapshot_ref,
            }
        )
        scroll_event = perform_exploratory_scroll(
            page=page,
            wait_ms=wait_ms,
            reason="Scroll candidate page while searching for inquiry form",
        )
        if scroll_event is not None:
            traces.append(scroll_event)
        channels = collect_contact_channels(page)
        traces.append(
            {
                "event_type": "browser_extract",
                "title": "Extract contact channels",
                "detail": (
                    f"emails={len(channels.get('emails') or [])}, "
                    f"phones={len(channels.get('phones') or [])}"
                ),
                "data": {
                    "url": normalize_url(str(page.url or "")) or target_url,
                    "title": page_title(page),
                    "candidate_rank": rank,
                    "contact_channels": channels,
                    **cursor_payload(page),
                },
                "snapshot_ref": snapshot_ref,
            }
        )
        form = find_best_form(page)
        if form is not None:
            return form, True, traces
    return None, bool(traces), traces

