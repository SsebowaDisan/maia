from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials
from api.services.agent.connectors.browser_contact.contact_channels import (
    cursor_payload,
    normalize_url,
    page_title,
    safe_text,
)
from api.services.agent.connectors.browser_contact.contact_navigation import (
    capture_navigation_snapshot,
    collect_navigation_candidates,
    perform_exploratory_scroll,
    rank_navigation_candidates,
)


def _page_excerpt(page: Any, *, max_len: int = 1800) -> str:
    try:
        text = str(page.evaluate("() => document.body ? document.body.innerText : ''") or "")
    except Exception:
        text = ""
    compact = " ".join(text.split()).strip()
    return compact[: max(120, int(max_len))]


def _goal_match_with_llm(
    *,
    goal_profile: dict[str, Any],
    page_payload: dict[str, Any],
) -> tuple[bool, float, str]:
    if not has_openai_credentials():
        return False, 0.0, "LLM credentials unavailable"
    payload = {
        "goal_profile": goal_profile,
        "page": page_payload,
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You evaluate whether a web page matches an autonomous navigation goal. "
                "Use semantic reasoning and return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only in this schema:\n"
                '{ "goal_match": true, "confidence": 0.0, "reason": "..." }\n'
                "Rules:\n"
                "- Use semantic understanding of the goal and page content.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- Keep confidence in [0,1].\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=260,
        )
    except Exception:
        return False, 0.0, "Goal evaluation failed"
    if not isinstance(response, dict):
        return False, 0.0, "Goal evaluation unavailable"
    goal_match = bool(response.get("goal_match"))
    try:
        confidence = max(0.0, min(1.0, float(response.get("confidence"))))
    except Exception:
        confidence = 0.0
    reason = safe_text(response.get("reason"), max_len=220)
    return goal_match, confidence, reason


def _page_goal_payload(page: Any) -> dict[str, Any]:
    return {
        "url": normalize_url(str(page.url or "")),
        "title": page_title(page),
        "excerpt": _page_excerpt(page, max_len=1800),
    }


def locate_goal_page_with_discovery(
    page: Any,
    *,
    goal_profile: dict[str, Any],
    wait_ms: int,
    timeout_ms: int = 12000,
    max_hops: int = 5,
    output_dir: Path | None = None,
    stamp_prefix: str = "",
) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {
        "goal_match": False,
        "confidence": 0.0,
        "reason": "",
        "goal_url": "",
    }

    current_payload = _page_goal_payload(page)
    match, confidence, reason = _goal_match_with_llm(
        goal_profile=goal_profile,
        page_payload=current_payload,
    )
    traces.append(
        {
            "event_type": "browser_extract",
            "title": "Evaluate current page against navigation goal",
            "detail": reason or "Assessing semantic goal match",
            "data": {
                "url": current_payload.get("url"),
                "title": current_payload.get("title"),
                "goal_profile": {
                    "goal": safe_text(goal_profile.get("goal"), max_len=180),
                    "success_criteria": goal_profile.get("success_criteria")
                    if isinstance(goal_profile.get("success_criteria"), list)
                    else [],
                },
                "goal_match": match,
                "goal_match_confidence": round(confidence, 3),
                **cursor_payload(page),
            },
            "snapshot_ref": None,
        }
    )
    if match and confidence >= 0.72:
        diagnostics.update(
            {
                "goal_match": True,
                "confidence": round(confidence, 3),
                "reason": reason,
                "goal_url": str(current_payload.get("url") or ""),
            }
        )
        return True, traces, diagnostics

    scroll_event = perform_exploratory_scroll(
        page=page,
        wait_ms=wait_ms,
        reason="Explore current page while seeking goal-matching destination",
    )
    if scroll_event is not None:
        traces.append(scroll_event)
        current_payload = _page_goal_payload(page)
        match, confidence, reason = _goal_match_with_llm(
            goal_profile=goal_profile,
            page_payload=current_payload,
        )
        traces.append(
            {
                "event_type": "browser_extract",
                "title": "Re-evaluate page after exploratory scroll",
                "detail": reason or "Assessing semantic goal match after scroll",
                "data": {
                    "url": current_payload.get("url"),
                    "title": current_payload.get("title"),
                    "goal_match": match,
                    "goal_match_confidence": round(confidence, 3),
                    **cursor_payload(page),
                },
                "snapshot_ref": None,
            }
        )
        if match and confidence >= 0.72:
            diagnostics.update(
                {
                    "goal_match": True,
                    "confidence": round(confidence, 3),
                    "reason": reason,
                    "goal_url": str(current_payload.get("url") or ""),
                }
            )
            return True, traces, diagnostics

    candidates = collect_navigation_candidates(page, max_items=max(max_hops * 8, 16))
    ranked_indexes = rank_navigation_candidates(candidates, max_hops=max_hops)
    if not ranked_indexes:
        return False, traces, diagnostics

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
                "title": "Navigate to goal candidate page",
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
        payload = _page_goal_payload(page)
        match, confidence, reason = _goal_match_with_llm(
            goal_profile=goal_profile,
            page_payload=payload,
        )
        traces.append(
            {
                "event_type": "browser_extract",
                "title": "Evaluate candidate page against navigation goal",
                "detail": reason or "Assessing semantic goal match",
                "data": {
                    "url": payload.get("url"),
                    "title": payload.get("title"),
                    "candidate_rank": rank,
                    "goal_match": match,
                    "goal_match_confidence": round(confidence, 3),
                    **cursor_payload(page),
                },
                "snapshot_ref": snapshot_ref,
            }
        )
        if match and confidence >= 0.72:
            diagnostics.update(
                {
                    "goal_match": True,
                    "confidence": round(confidence, 3),
                    "reason": reason,
                    "goal_url": str(payload.get("url") or ""),
                }
            )
            return True, traces, diagnostics
    return False, traces, diagnostics

