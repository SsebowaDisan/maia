from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials


def first_visible(scope: Any, selectors: list[str]) -> Any | None:
    for selector in selectors:
        try:
            loc = scope.locator(selector)
            if loc.count() <= 0:
                continue
            candidate = loc.first
            if hasattr(candidate, "is_visible") and not candidate.is_visible():
                continue
            return candidate
        except Exception:
            continue
    return None


def _safe_text(value: Any, *, max_len: int = 180) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:max_len]


def _page_title(page: Any) -> str:
    try:
        return _safe_text(page.title(), max_len=180)
    except Exception:
        return ""


def _cursor_payload(page: Any) -> dict[str, float]:
    try:
        viewport = page.evaluate(
            "() => ({ width: Number(window.innerWidth || 1366), height: Number(window.innerHeight || 768) })"
        )
        width = float(viewport.get("width") or 1366)
        height = float(viewport.get("height") or 768)
    except Exception:
        width = 1366.0
        height = 768.0
    return {
        "cursor_x": max(24.0, min(width - 24.0, width * 0.52)),
        "cursor_y": max(24.0, min(height - 24.0, height * 0.22)),
    }


def _normalize_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return text


def _collect_navigation_candidates(page: Any, *, max_items: int) -> list[dict[str, Any]]:
    try:
        current_url = _normalize_url(str(page.url or ""))
    except Exception:
        current_url = ""
    host = (urlparse(current_url).hostname or "").strip().lower()
    if not host:
        return []
    try:
        raw = page.evaluate(
            """
            ({ maxItems }) => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const rows = [];
                const seen = new Set();
                const nodes = Array.from(document.querySelectorAll("a[href]"));
                for (const node of nodes) {
                    if (!node || rows.length >= maxItems) break;
                    const href = normalize(node.getAttribute("href"));
                    if (!href || href.startsWith("#") || href.startsWith("javascript:")) continue;
                    if (href.startsWith("mailto:") || href.startsWith("tel:")) continue;
                    let absolute = "";
                    try {
                        absolute = new URL(href, window.location.href).href;
                    } catch {
                        continue;
                    }
                    if (!absolute || seen.has(absolute)) continue;
                    const rect = node.getBoundingClientRect();
                    const style = window.getComputedStyle(node);
                    const visible =
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== "hidden" &&
                        style.display !== "none";
                    if (!visible) continue;
                    const label = normalize(node.innerText || node.textContent || "") ||
                        normalize(node.getAttribute("aria-label")) ||
                        normalize(node.getAttribute("title"));
                    rows.push({
                        url: absolute,
                        label,
                        in_navigation: Boolean(node.closest("nav, header, footer")),
                        depth_hint: absolute.split("/").filter(Boolean).length,
                    });
                    seen.add(absolute);
                }
                return rows;
            }
            """,
            {"maxItems": max(8, int(max_items))},
        )
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        candidate_url = _normalize_url(item.get("url"))
        if not candidate_url or candidate_url in seen:
            continue
        parsed = urlparse(candidate_url)
        candidate_host = (parsed.hostname or "").strip().lower()
        if candidate_host != host and not candidate_host.endswith(f".{host}"):
            continue
        seen.add(candidate_url)
        rows.append(
            {
                "url": candidate_url,
                "label": _safe_text(item.get("label"), max_len=180),
                "in_navigation": bool(item.get("in_navigation")),
                "depth_hint": int(item.get("depth_hint") or 0),
            }
        )
    return rows[: max(8, int(max_items))]


def _rank_candidates_with_llm(candidates: list[dict[str, Any]], *, max_hops: int) -> list[int]:
    if not candidates:
        return []
    default_order = list(range(min(len(candidates), max(1, int(max_hops)))))
    if not has_openai_credentials():
        return default_order
    compact_rows = [
        {
            "index": idx,
            "url": row.get("url"),
            "label": row.get("label"),
            "in_navigation": bool(row.get("in_navigation")),
            "depth_hint": int(row.get("depth_hint") or 0),
        }
        for idx, row in enumerate(candidates[:40])
    ]
    try:
        response = call_json_response(
            system_prompt=(
                "You choose website navigation candidates to reach a page where a user can submit an inquiry form. "
                "Return JSON only."
            ),
            user_prompt=(
                "Pick the best candidate indexes to visit in order.\n"
                "Return JSON only:\n"
                '{ "candidate_indexes":[0,1,2], "reason":"..." }\n'
                "Rules:\n"
                "- Prioritize pages most likely to contain an inquiry/request form.\n"
                "- Use only provided indexes.\n"
                "- Keep order from highest to lowest confidence.\n\n"
                f"Candidates:\n{compact_rows!r}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=260,
        )
    except Exception:
        return default_order
    if not isinstance(response, dict):
        return default_order
    raw_indexes = response.get("candidate_indexes")
    if not isinstance(raw_indexes, list):
        return default_order
    ranked: list[int] = []
    for raw in raw_indexes[:24]:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx < 0 or idx >= len(candidates):
            continue
        if idx in ranked:
            continue
        ranked.append(idx)
        if len(ranked) >= max(1, int(max_hops)):
            break
    for fallback in default_order:
        if fallback in ranked:
            continue
        ranked.append(fallback)
        if len(ranked) >= max(1, int(max_hops)):
            break
    return ranked


def _score_form_candidate(form: Any) -> float:
    try:
        control_count = int(form.locator("input, textarea, select").count())
    except Exception:
        control_count = 0
    if control_count <= 0:
        return 0.0
    try:
        text_like_count = int(
            form.locator("input:not([type]), input[type='text'], input[type='email'], input[type='tel'], textarea")
            .count()
        )
    except Exception:
        text_like_count = 0
    try:
        textarea_count = int(form.locator("textarea").count())
    except Exception:
        textarea_count = 0
    try:
        submit_count = int(form.locator("button[type='submit'], input[type='submit']").count())
    except Exception:
        submit_count = 0
    score = 0.0
    if control_count >= 2:
        score += 1.0
    if text_like_count >= 2:
        score += 1.0
    if textarea_count > 0:
        score += 1.0
    if submit_count > 0:
        score += 1.0
    if control_count >= 4:
        score += 0.8
    return score


def _find_best_form(page: Any) -> Any | None:
    try:
        forms = page.locator("form")
        total = min(forms.count(), 16)
    except Exception:
        return None
    best_form: Any | None = None
    best_score = 0.0
    for idx in range(total):
        form = forms.nth(idx)
        score = _score_form_candidate(form)
        if score <= best_score:
            continue
        best_form = form
        best_score = score
    if best_score < 2.8:
        return None
    return best_form


def _capture_navigation_snapshot(
    *,
    page: Any,
    output_dir: Path | None,
    stamp_prefix: str,
    hop_index: int,
) -> str | None:
    if output_dir is None:
        return None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{stamp_prefix}-contact-nav-{hop_index:02d}.png" if stamp_prefix else f"contact-nav-{hop_index:02d}.png"
        target = output_dir / filename
        page.screenshot(path=str(target), full_page=True)
        return str(target)
    except Exception:
        return None


def locate_contact_form(
    page: Any,
    *,
    wait_ms: int,
    timeout_ms: int = 12000,
    max_hops: int = 5,
    output_dir: Path | None = None,
    stamp_prefix: str = "",
) -> tuple[Any | None, bool, list[dict[str, Any]]]:
    traces: list[dict[str, Any]] = []
    form = _find_best_form(page)
    if form is not None:
        return form, False, traces

    candidates = _collect_navigation_candidates(page, max_items=max(max_hops * 8, 16))
    ranked_indexes = _rank_candidates_with_llm(candidates, max_hops=max_hops)
    if not ranked_indexes:
        return None, False, traces

    visited: set[str] = set()
    for rank, candidate_index in enumerate(ranked_indexes, start=1):
        candidate = candidates[candidate_index]
        target_url = _normalize_url(candidate.get("url"))
        if not target_url or target_url in visited:
            continue
        visited.add(target_url)
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=max(4000, int(timeout_ms)))
            page.wait_for_timeout(max(250, int(wait_ms)))
        except Exception:
            continue
        snapshot_ref = _capture_navigation_snapshot(
            page=page,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
            hop_index=rank,
        )
        traces.append(
            {
                "event_type": "browser_navigate",
                "title": "Navigate to likely inquiry page",
                "detail": _safe_text(candidate.get("label") or target_url, max_len=200),
                "data": {
                    "url": _normalize_url(str(page.url or "")) or target_url,
                    "title": _page_title(page),
                    "candidate_rank": rank,
                    "candidate_index": candidate_index,
                    "candidate_url": target_url,
                    **_cursor_payload(page),
                },
                "snapshot_ref": snapshot_ref,
            }
        )
        form = _find_best_form(page)
        if form is not None:
            return form, True, traces
    return None, bool(traces), traces
