from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from ktem.db.models import engine

from api.context import ApiContext

from .constants import API_FAST_QA_MAX_CHUNKS_PER_SOURCE, API_FAST_QA_MAX_SOURCES


def _page_label_sort_key(raw: Any) -> int:
    text = " ".join(str(raw or "").split()).strip()
    if not text:
        return 0
    if text.isdigit():
        try:
            return max(0, int(text))
        except Exception:
            return 0
    # Accept labels like "Page 3", "p.12", "12/40", etc.
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
    if parsed != parsed:  # NaN
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
        key = (
            normalized["x"],
            normalized["y"],
            normalized["width"],
            normalized["height"],
        )
        if key in seen:
            continue
        seen.add(key)
        boxes.append(normalized)
        if len(boxes) >= 24:
            break
    return boxes


def load_recent_chunks_for_fast_qa(
    context: ApiContext,
    user_id: str,
    selected_payload: dict[str, list[Any]],
    query: str,
    max_sources: int = 48,
    max_chunks: int = 10,
) -> list[dict[str, Any]]:
    try:
        index = context.get_index(None)
        Source = index._resources["Source"]
        IndexTable = index._resources["Index"]
        doc_store = index._resources["DocStore"]
    except Exception:
        return []

    selected = selected_payload.get(str(index.id), ["all", [], user_id])
    mode = selected[0] if isinstance(selected, list) and selected else "all"
    selected_ids = selected[1] if isinstance(selected, list) and len(selected) > 1 else []
    selected_ids = [str(item) for item in selected_ids] if isinstance(selected_ids, list) else []

    source_ids: list[str] = []
    source_name_by_id: dict[str, str] = {}
    source_scan = max(1, int(max_sources))
    chunk_limit = max(1, int(max_chunks))
    with Session(engine) as session:
        if mode == "disabled":
            return []

        if mode == "select" and selected_ids:
            stmt = select(Source.id, Source.name).where(Source.id.in_(selected_ids))
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            rows = session.execute(stmt).all()
            for row in rows:
                source_id = str(row[0])
                source_ids.append(source_id)
                source_name_by_id[source_id] = str(row[1])
        else:
            stmt = select(Source.id, Source.name).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            rows = session.execute(stmt.limit(source_scan)).all()
            for row in rows:
                source_id = str(row[0])
                source_ids.append(source_id)
                source_name_by_id[source_id] = str(row[1])

        if not source_ids:
            return []

        rel_stmt = (
            select(IndexTable.target_id, IndexTable.source_id)
            .where(
                IndexTable.relation_type == "document",
                IndexTable.source_id.in_(source_ids),
            )
            .limit(max(chunk_limit * 18, source_scan * 4))
        )
        rel_rows = session.execute(rel_stmt).all()

    if not rel_rows:
        return []

    target_to_source: dict[str, str] = {}
    target_ids: list[str] = []
    for target_id, source_id in rel_rows:
        target_key = str(target_id)
        source_key = str(source_id)
        target_to_source[target_key] = source_key
        target_ids.append(target_key)

    try:
        docs = doc_store.get(target_ids)
    except Exception:
        return []

    stopwords = {
        "about",
        "document",
        "file",
        "pdf",
        "summary",
        "summarize",
        "overview",
        "describe",
        "this",
        "that",
        "what",
        "which",
        "with",
        "from",
        "tell",
    }
    query_terms = [
        t for t in re.findall(r"[a-zA-Z0-9]+", query.lower()) if len(t) > 2 and t not in stopwords
    ][:16]
    broad_query = len(query_terms) <= 2

    scored_text: list[dict[str, Any]] = []
    image_by_source: dict[str, dict[str, Any]] = {}
    for doc in docs or []:
        doc_id = str(getattr(doc, "doc_id", "") or "")
        if not doc_id:
            continue

        metadata = getattr(doc, "metadata", {}) or {}
        doc_type = str(metadata.get("type", "") or "")
        page_label = str(metadata.get("page_label", "") or "")
        highlight_boxes = _extract_highlight_boxes(metadata)

        source_id = target_to_source.get(doc_id, "")
        source_name = str(metadata.get("file_name", "") or "") or source_name_by_id.get(
            source_id,
            "Indexed file",
        )
        source_name_lower = source_name.lower()
        source_key = source_id or f"name:{source_name}"

        image_origin = metadata.get("image_origin")
        if isinstance(image_origin, str) and image_origin.startswith("data:image/"):
            existing = image_by_source.get(source_key)
            if existing is None or (
                doc_type == "thumbnail" and existing.get("doc_type") != "thumbnail"
            ):
                image_by_source[source_key] = {
                    "source_id": source_id,
                    "source_name": source_name,
                    "doc_type": doc_type,
                    "page_label": page_label,
                    "image_origin": image_origin,
                }

        raw_text = str(getattr(doc, "text", "") or "")
        text = re.sub(r"\s+", " ", raw_text).strip()
        if not text:
            continue
        if doc_type == "thumbnail" and len(text) <= 20:
            continue

        lowered = text.lower()
        score = sum(lowered.count(term) for term in query_terms)
        score += 4 * sum(source_name_lower.count(term) for term in query_terms)
        if doc_type == "ocr":
            score += 4
        elif doc_type == "table":
            score += 2
        elif doc_type == "image":
            score += 2
        if broad_query:
            score += min(len(text) // 80, 10)
        if "pdf" in query_terms and source_name_lower.endswith(".pdf"):
            score += 8
        if source_name_lower.startswith("http://") or source_name_lower.startswith("https://"):
            score -= 1

        scored_text.append(
            {
                "score": score,
                "source_id": source_id,
                "source_key": source_key,
                "source_name": source_name,
                "text": text[:1200],
                "doc_type": doc_type,
                "page_label": page_label,
                "image_origin": image_by_source.get(source_key, {}).get("image_origin"),
                "highlight_boxes": highlight_boxes,
                "llm_trulens_score": _to_float(metadata.get("llm_trulens_score")) or 0.0,
                "rerank_score": _to_float(metadata.get("rerank_score")) or 0.0,
                "vector_score": (
                    _to_float(metadata.get("vector_score"))
                    or _to_float(metadata.get("score"))
                    or 0.0
                ),
                "is_exact_match": bool(metadata.get("is_exact_match", False)),
            }
        )

    if not scored_text and not image_by_source:
        return []

    # Backfill image payload after full pass so thumbnail/text ordering does not matter.
    for item in scored_text:
        if item.get("image_origin"):
            continue
        source_key = str(item.get("source_key", ""))
        item["image_origin"] = image_by_source.get(source_key, {}).get("image_origin")

    # For direct file-scoped queries, include broad context instead of strict keyword slices.
    if mode == "select" and selected_ids:
        scored_text.sort(
            key=lambda item: (
                item.get("source_name", ""),
                _page_label_sort_key(item.get("page_label")),
                -len(str(item.get("text", ""))),
            )
        )
        selected_text = scored_text[: chunk_limit * 2]
    else:
        scored_text.sort(key=lambda item: int(item.get("score", 0)), reverse=True)
        source_cap = max(1, int(API_FAST_QA_MAX_CHUNKS_PER_SOURCE))
        max_distinct_sources = max(1, int(API_FAST_QA_MAX_SOURCES))
        selected_text = []
        per_source_count: dict[str, int] = {}
        for item in scored_text:
            source_key = str(item.get("source_key", ""))
            if not source_key:
                continue
            source_seen = source_key in per_source_count
            if not source_seen and len(per_source_count) >= max_distinct_sources:
                continue
            source_hits = per_source_count.get(source_key, 0)
            if source_hits >= source_cap:
                continue
            selected_text.append(item)
            per_source_count[source_key] = source_hits + 1
            if len(selected_text) >= chunk_limit:
                break
        if len(selected_text) < chunk_limit:
            for item in scored_text:
                if item in selected_text:
                    continue
                selected_text.append(item)
                if len(selected_text) >= chunk_limit:
                    break

    # Add image-only sources if no text was selected from that source.
    selected_sources = {str(item.get("source_key", "")) for item in selected_text}
    for source_key, image_payload in image_by_source.items():
        if source_key in selected_sources:
            continue
        selected_text.append(
            {
                "score": -1,
                "source_id": str(image_payload.get("source_id", "") or ""),
                "source_key": source_key,
                "source_name": str(image_payload.get("source_name", "") or "Indexed file"),
                "text": "Image evidence available for visual analysis.",
                "doc_type": str(image_payload.get("doc_type", "") or "thumbnail"),
                "page_label": str(image_payload.get("page_label", "") or ""),
                "image_origin": image_payload.get("image_origin"),
                "highlight_boxes": [],
            }
        )

    return selected_text
