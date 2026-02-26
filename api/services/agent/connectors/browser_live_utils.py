from __future__ import annotations

from collections import Counter
from typing import Any

_STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "before",
    "being",
    "between",
    "company",
    "could",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "page",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
    "your",
    "http",
    "https",
    "www",
}


def extract_keywords(text: str, *, limit: int = 8) -> list[str]:
    words = [
        "".join(ch for ch in token.lower() if ch.isalnum() or ch in ("_", "-"))
        for token in str(text or "").split()
    ]
    filtered = [word for word in words if len(word) >= 4 and word not in _STOPWORDS]
    counts = Counter(filtered)
    return [word for word, _ in counts.most_common(max(1, int(limit)))]


def excerpt(text: str, *, limit: int = 420) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(1, limit - 1)].rstrip()}..."


def to_number(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def safe_focus_point(
    *,
    page: Any,
    pass_index: int,
    viewport_width: float,
    viewport_height: float,
) -> tuple[float, float]:
    fallback_x = 140 + ((pass_index + 1) * 170) % max(220, int(viewport_width) - 120)
    fallback_y = 170 + ((pass_index + 1) * 90) % max(200, int(viewport_height) - 120)
    fallback_x = max(48.0, min(viewport_width - 48.0, float(fallback_x)))
    fallback_y = max(96.0, min(viewport_height - 60.0, float(fallback_y)))
    try:
        payload = page.evaluate(
            """(index) => {
                const candidates = Array.from(
                    document.querySelectorAll("h1,h2,h3,h4,p,li,a,button,[role='button']")
                );
                const points = [];
                for (const el of candidates) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const text = (el.innerText || el.textContent || "").trim();
                    if (!text) continue;
                    if (style.visibility === "hidden" || style.display === "none") continue;
                    if (rect.width < 24 || rect.height < 12) continue;
                    if (rect.bottom < 8 || rect.top > window.innerHeight - 8) continue;
                    const centerX = Math.max(8, Math.min(window.innerWidth - 8, rect.left + rect.width / 2));
                    const centerY = Math.max(8, Math.min(window.innerHeight - 8, rect.top + Math.min(rect.height / 2, 60)));
                    points.push({ x: centerX, y: centerY });
                    if (points.length >= 20) break;
                }
                if (!points.length) return null;
                return points[Math.abs(Number(index || 0)) % points.length];
            }""",
            pass_index,
        )
        if isinstance(payload, dict):
            x = max(8.0, min(viewport_width - 8.0, to_number(payload.get("x"), fallback_x)))
            y = max(8.0, min(viewport_height - 8.0, to_number(payload.get("y"), fallback_y)))
            return x, y
    except Exception:
        pass
    return fallback_x, fallback_y


def smart_scroll_delta(
    *,
    metrics_before: dict[str, float],
    pass_index: int,
    total_passes: int,
) -> float:
    scroll_top = to_number(metrics_before.get("scroll_top"), 0.0)
    scroll_height = to_number(metrics_before.get("scroll_height"), 0.0)
    viewport_height = max(1.0, to_number(metrics_before.get("viewport_height"), 768.0))
    max_scroll = max(0.0, scroll_height - viewport_height)
    if max_scroll <= 1.0:
        return 0.0
    remaining_down = max_scroll - scroll_top
    is_last_pass = pass_index >= max(0, total_passes - 1)
    if is_last_pass:
        return -min(scroll_top, viewport_height * 0.6)
    if remaining_down <= viewport_height * 0.65:
        return -min(scroll_top, viewport_height * 0.4)
    return min(remaining_down, viewport_height * 0.88)


def keyword_regions(
    *,
    page: Any,
    keywords: list[str],
    limit: int = 8,
) -> list[dict[str, float | str]]:
    normalized = [item.strip().lower() for item in keywords if item and item.strip()]
    if not normalized:
        return []
    try:
        payload = page.evaluate(
            """(terms, maxItems) => {
                const nodes = Array.from(document.querySelectorAll("h1,h2,h3,h4,p,li,a,button,span"));
                const out = [];
                const seen = new Set();
                for (const term of terms || []) {
                    if (!term) continue;
                    for (const el of nodes) {
                        const text = (el.innerText || el.textContent || "").toLowerCase();
                        if (!text.includes(term)) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 20 || rect.height < 10) continue;
                        if (rect.bottom < 4 || rect.top > window.innerHeight - 4) continue;
                        const x = Math.max(0, Math.min(100, (rect.left / Math.max(1, window.innerWidth)) * 100));
                        const y = Math.max(0, Math.min(100, (rect.top / Math.max(1, window.innerHeight)) * 100));
                        const w = Math.max(2, Math.min(100, (rect.width / Math.max(1, window.innerWidth)) * 100));
                        const h = Math.max(2, Math.min(100, (rect.height / Math.max(1, window.innerHeight)) * 100));
                        const signature = `${term}:${Math.round(x)}:${Math.round(y)}`;
                        if (seen.has(signature)) continue;
                        seen.add(signature);
                        out.push({ keyword: term, x, y, width: w, height: h });
                        break;
                    }
                    if (out.length >= Math.max(1, Number(maxItems || 1))) break;
                }
                return out;
            }""",
            normalized[: max(1, int(limit))],
            limit,
        )
        if isinstance(payload, list):
            rows: list[dict[str, float | str]] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                keyword = str(item.get("keyword") or "").strip()
                if not keyword:
                    continue
                rows.append(
                    {
                        "keyword": keyword,
                        "x": max(0.0, min(100.0, to_number(item.get("x"), 0.0))),
                        "y": max(0.0, min(100.0, to_number(item.get("y"), 0.0))),
                        "width": max(1.0, min(100.0, to_number(item.get("width"), 1.0))),
                        "height": max(1.0, min(100.0, to_number(item.get("height"), 1.0))),
                    }
                )
            return rows
    except Exception:
        return []
    return []
