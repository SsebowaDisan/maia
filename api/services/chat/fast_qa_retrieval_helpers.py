from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .constants import API_FAST_QA_MAX_CHUNKS_PER_SOURCE, API_FAST_QA_MAX_SOURCES

_QUERY_URL_RE = re.compile(r"https?://[^\s\])>\"']+", flags=re.IGNORECASE)


def _normalize_host(raw_value: Any) -> str:
    text = str(raw_value or "").strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    host = (parsed.netloc or "").strip().lower()
    if not host:
        return ""
    if "@" in host:
        host = host.split("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _extract_target_hosts(query: str) -> list[str]:
    seen: set[str] = set()
    hosts: list[str] = []
    for match in _QUERY_URL_RE.finditer(str(query or "")):
        host = _normalize_host(match.group(0))
        if not host or host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return hosts


def _host_matches_target(host: str, target_hosts: set[str]) -> bool:
    if not host or not target_hosts:
        return False
    for target_host in target_hosts:
        if host == target_host:
            return True
        if host.endswith(f".{target_host}") or target_host.endswith(f".{host}"):
            return True
    return False


def _matches_target_hosts(
    *,
    source_name: str,
    metadata: dict[str, Any],
    target_hosts: set[str],
) -> bool:
    if not target_hosts:
        return False
    host_candidates = {
        _normalize_host(source_name),
        _normalize_host(metadata.get("page_url")),
        _normalize_host(metadata.get("source_url")),
        _normalize_host(metadata.get("file_name")),
    }
    return any(_host_matches_target(host, target_hosts) for host in host_candidates if host)


def _extract_query_terms(query: str, *, max_terms: int = 20) -> list[str]:
    ordered_terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[a-zA-Z0-9]+", str(query or "").lower()):
        if len(token) < 3 or token.isdigit():
            continue
        if token in seen:
            continue
        seen.add(token)
        ordered_terms.append(token)
        if len(ordered_terms) >= max_terms:
            break
    return ordered_terms


def _page_label_sort_key(raw: Any) -> int:
    text = " ".join(str(raw or "").split()).strip()
    if not text:
        return 0
    if text.isdigit():
        try:
            return max(0, int(text))
        except Exception:
            return 0
    matches = re.findall(r"\d+", text)
    if not matches:
        return 0
    try:
        return max(0, int(matches[0]))
    except Exception:
        return 0


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed


def _normalize_xywh(
    *,
    x: Any,
    y: Any,
    width: Any,
    height: Any,
    page_width: float | None,
    page_height: float | None,
) -> dict[str, float] | None:
    left = _to_float(x)
    top = _to_float(y)
    w = _to_float(width)
    h = _to_float(height)
    if left is None or top is None or w is None or h is None:
        return None
    if (
        page_width
        and page_height
        and page_width > 1.0
        and page_height > 1.0
        and (left > 1.0 or top > 1.0 or w > 1.0 or h > 1.0)
    ):
        left /= page_width
        top /= page_height
        w /= page_width
        h /= page_height
    left = max(0.0, min(1.0, left))
    top = max(0.0, min(1.0, top))
    w = max(0.0, min(1.0 - left, w))
    h = max(0.0, min(1.0 - top, h))
    if w < 0.002 or h < 0.002:
        return None
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "width": round(w, 6),
        "height": round(h, 6),
    }


def _normalize_xyxy(
    *,
    x0: Any,
    y0: Any,
    x1: Any,
    y1: Any,
    page_width: float | None,
    page_height: float | None,
) -> dict[str, float] | None:
    left = _to_float(x0)
    top = _to_float(y0)
    right = _to_float(x1)
    bottom = _to_float(y1)
    if left is None or top is None or right is None or bottom is None:
        return None
    width = right - left
    height = bottom - top
    return _normalize_xywh(
        x=left,
        y=top,
        width=width,
        height=height,
        page_width=page_width,
        page_height=page_height,
    )


def _normalize_points_box(
    points: Any,
    *,
    page_width: float | None,
    page_height: float | None,
) -> dict[str, float] | None:
    if not isinstance(points, list) or len(points) < 2:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            px = _to_float(point[0])
            py = _to_float(point[1])
        elif isinstance(point, dict):
            px = _to_float(point.get("x"))
            py = _to_float(point.get("y"))
        else:
            px = None
            py = None
        if px is None or py is None:
            continue
        xs.append(px)
        ys.append(py)
    if len(xs) < 2 or len(ys) < 2:
        return None
    return _normalize_xyxy(
        x0=min(xs),
        y0=min(ys),
        x1=max(xs),
        y1=max(ys),
        page_width=page_width,
        page_height=page_height,
    )


def _extract_highlight_boxes(metadata: dict[str, Any]) -> list[dict[str, float]]:
    page_width = _to_float(metadata.get("page_width") or metadata.get("pdf_page_width"))
    page_height = _to_float(metadata.get("page_height") or metadata.get("pdf_page_height"))

    candidates: list[Any] = []
    for key in ("highlight_boxes", "boxes", "box", "bbox", "bounding_box", "location", "coordinates"):
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            if key in ("box", "bbox", "bounding_box") and len(value) == 4 and not isinstance(value[0], (list, dict, tuple)):
                candidates.append(value)
            else:
                candidates.extend(value)
        else:
            candidates.append(value)

    boxes: list[dict[str, float]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for candidate in candidates:
        normalized: dict[str, float] | None = None
        if isinstance(candidate, dict):
            if {"x", "y", "width", "height"}.issubset(candidate):
                normalized = _normalize_xywh(
                    x=candidate.get("x"),
                    y=candidate.get("y"),
                    width=candidate.get("width"),
                    height=candidate.get("height"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif {"x0", "y0", "x1", "y1"}.issubset(candidate):
                normalized = _normalize_xyxy(
                    x0=candidate.get("x0"),
                    y0=candidate.get("y0"),
                    x1=candidate.get("x1"),
                    y1=candidate.get("y1"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif {"l", "t", "r", "b"}.issubset(candidate):
                normalized = _normalize_xyxy(
                    x0=candidate.get("l"),
                    y0=candidate.get("t"),
                    x1=candidate.get("r"),
                    y1=candidate.get("b"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif isinstance(candidate.get("points"), list):
                normalized = _normalize_points_box(
                    candidate.get("points"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif isinstance(candidate.get("location"), list):
                normalized = _normalize_points_box(
                    candidate.get("location"),
                    page_width=page_width,
                    page_height=page_height,
                )
        elif isinstance(candidate, (list, tuple)):
            if len(candidate) == 4:
                normalized = _normalize_xyxy(
                    x0=candidate[0],
                    y0=candidate[1],
                    x1=candidate[2],
                    y1=candidate[3],
                    page_width=page_width,
                    page_height=page_height,
                )
            else:
                normalized = _normalize_points_box(
                    list(candidate),
                    page_width=page_width,
                    page_height=page_height,
                )

        if not normalized:
            continue
        key = (normalized["x"], normalized["y"], normalized["width"], normalized["height"])
        if key in seen:
            continue
        seen.add(key)
        boxes.append(normalized)
        if len(boxes) >= 24:
            break
    return boxes


def _extract_evidence_units(metadata: dict[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    raw_units = metadata.get("evidence_units")
    if not isinstance(raw_units, list) or not raw_units:
        return []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_unit in raw_units:
        if not isinstance(raw_unit, dict):
            continue
        text = re.sub(r"\s+", " ", str(raw_unit.get("text", "") or "")).strip()
        if len(text) < 8:
            continue
        boxes = _extract_highlight_boxes(raw_unit)
        if not boxes:
            continue
        char_start = _to_intish(raw_unit.get("char_start"))
        char_end = _to_intish(raw_unit.get("char_end"))
        key = f"{char_start or 0}|{char_end or 0}|{text[:120].lower()}"
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {
            "text": text[:240],
            "highlight_boxes": boxes,
        }
        if char_start is not None and char_start > 0:
            item["char_start"] = char_start
        if char_end is not None and char_start is not None and char_end > char_start:
            item["char_end"] = char_end
        output.append(item)
        if len(output) >= max(1, int(limit)):
            break
    return output


def _to_intish(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed


def _ranked_chunk_selection(rows: list[dict[str, Any]], *, chunk_limit: int) -> list[dict[str, Any]]:
    ranked_rows = sorted(rows, key=lambda item: int(item.get("score", 0)), reverse=True)
    source_cap = max(1, int(API_FAST_QA_MAX_CHUNKS_PER_SOURCE))
    max_distinct_sources = max(1, int(API_FAST_QA_MAX_SOURCES))
    chosen: list[dict[str, Any]] = []
    per_source_count: dict[str, int] = {}
    seen_source_pages: set[tuple[str, str]] = set()

    for item in ranked_rows:
        source_key = str(item.get("source_key", ""))
        if not source_key:
            continue
        page_key = str(item.get("page_label", "") or "")
        source_seen = source_key in per_source_count
        if not source_seen and len(per_source_count) >= max_distinct_sources:
            continue
        source_hits = per_source_count.get(source_key, 0)
        if source_hits >= source_cap:
            continue
        if page_key:
            pair = (source_key, page_key)
            if pair in seen_source_pages:
                continue
            seen_source_pages.add(pair)
        chosen.append(item)
        per_source_count[source_key] = source_hits + 1
        if len(chosen) >= chunk_limit:
            return chosen

    for item in ranked_rows:
        source_key = str(item.get("source_key", ""))
        if not source_key:
            continue
        source_seen = source_key in per_source_count
        if not source_seen and len(per_source_count) >= max_distinct_sources:
            continue
        source_hits = per_source_count.get(source_key, 0)
        if source_hits >= source_cap:
            continue
        chosen.append(item)
        per_source_count[source_key] = source_hits + 1
        if len(chosen) >= chunk_limit:
            break
    if len(chosen) < chunk_limit:
        for item in ranked_rows:
            if item in chosen:
                continue
            chosen.append(item)
            if len(chosen) >= chunk_limit:
                break
    return chosen
