from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

from .contact_channels import cursor_payload, normalize_url, page_title, safe_text


def collect_navigation_candidates(page: Any, *, max_items: int) -> list[dict[str, Any]]:
    try:
        current_url = normalize_url(str(page.url or ""))
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
                    const label =
                        normalize(node.innerText || node.textContent || "") ||
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
        candidate_url = normalize_url(item.get("url"))
        if not candidate_url or candidate_url in seen:
            continue
        candidate_host = (urlparse(candidate_url).hostname or "").strip().lower()
        if candidate_host != host and not candidate_host.endswith(f".{host}"):
            continue
        seen.add(candidate_url)
        rows.append(
            {
                "url": candidate_url,
                "label": safe_text(item.get("label"), max_len=180),
                "in_navigation": bool(item.get("in_navigation")),
                "depth_hint": int(item.get("depth_hint") or 0),
            }
        )
    return rows[: max(8, int(max_items))]


def rank_navigation_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_hops: int,
) -> list[int]:
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
                "You rank website navigation links to maximize the chance of finding a live inquiry form. "
                "Return JSON only."
            ),
            user_prompt=(
                "Return JSON only in this schema:\n"
                '{ "candidate_indexes":[0,1,2], "reason":"..." }\n'
                "Rules:\n"
                "- Use only candidate indexes from input.\n"
                "- Prioritize pages that likely contain a form with submit capability.\n"
                "- Return highest confidence first.\n\n"
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


def capture_navigation_snapshot(
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
        filename = (
            f"{stamp_prefix}-contact-nav-{hop_index:02d}.png"
            if stamp_prefix
            else f"contact-nav-{hop_index:02d}.png"
        )
        target = output_dir / filename
        page.screenshot(path=str(target), full_page=True)
        return str(target)
    except Exception:
        return None


def _scroll_metrics(page: Any) -> dict[str, float]:
    try:
        payload = page.evaluate(
            """
            () => ({
                scroll_top: Number(window.scrollY || document.documentElement.scrollTop || 0),
                scroll_height: Number(
                    Math.max(
                        document.body ? document.body.scrollHeight : 0,
                        document.documentElement ? document.documentElement.scrollHeight : 0
                    ) || 0
                ),
                viewport_height: Number(window.innerHeight || 768),
            })
            """
        )
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "scroll_top": float(payload.get("scroll_top") or 0.0),
        "scroll_height": float(payload.get("scroll_height") or 0.0),
        "viewport_height": max(1.0, float(payload.get("viewport_height") or 768.0)),
    }


def perform_exploratory_scroll(
    *,
    page: Any,
    wait_ms: int,
    reason: str,
) -> dict[str, Any] | None:
    before = _scroll_metrics(page)
    max_scroll = max(0.0, before["scroll_height"] - before["viewport_height"])
    if max_scroll <= 1.0:
        return None
    delta = min(max(220.0, before["viewport_height"] * 0.6), max_scroll)
    try:
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(max(180, int(wait_ms) // 2))
    except Exception:
        return None
    after = _scroll_metrics(page)
    moved = after["scroll_top"] - before["scroll_top"]
    if abs(moved) < 1.0:
        return None
    direction = "down" if moved > 0 else "up"
    denominator = max(1.0, after["scroll_height"] - after["viewport_height"])
    return {
        "event_type": "browser_scroll",
        "title": "Explore page content",
        "detail": reason,
        "data": {
            "url": normalize_url(str(page.url or "")),
            "title": page_title(page),
            "scroll_direction": direction,
            "scroll_percent": round((after["scroll_top"] / denominator) * 100.0, 2),
            **cursor_payload(page),
        },
        "snapshot_ref": None,
    }

