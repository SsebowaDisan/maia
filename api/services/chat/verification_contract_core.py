from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

VERIFICATION_CONTRACT_VERSION = "2026-03-08.v1"


def _clean_text(value: Any, *, max_len: int = 240) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, int(max_len))]


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed


def _to_int(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed


def _normalize_url(raw_value: Any) -> str:
    text = _clean_text(raw_value, max_len=2048).strip(" <>\"'`")
    if not text:
        return ""
    text = text.rstrip(".,;:!?")
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _normalize_source_type(
    *,
    source_type: Any,
    source_name: Any,
    source_url: str,
    file_id: str,
) -> str:
    lowered = _clean_text(source_type, max_len=48).lower()
    if lowered in {"web", "website", "url", "site"}:
        return "web"
    if lowered in {"pdf"}:
        return "pdf"
    if lowered in {"image", "img"}:
        return "image"
    if lowered in {"doc", "document", "docs"}:
        return "doc"
    if lowered in {"sheet", "sheets", "spreadsheet"}:
        return "sheet"
    if source_url:
        if source_url.lower().endswith(".pdf"):
            return "pdf"
        return "web"
    source_label = _clean_text(source_name, max_len=220).lower()
    if source_label.endswith(".pdf"):
        return "pdf"
    if source_label.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return "image"
    if file_id:
        return "file"
    return "unknown"


def _normalize_ref_ids(value: Any, *, max_items: int = 10, max_len: int = 180) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    output: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, list):
            nested = _normalize_ref_ids(row, max_items=max_items, max_len=max_len)
            for nested_row in nested:
                lowered = nested_row.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                output.append(nested_row)
                if len(output) >= max(1, int(max_items)):
                    return output
            continue
        text = _clean_text(row, max_len=max_len)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(text)
        if len(output) >= max(1, int(max_items)):
            break
    return output


def _normalize_highlight_boxes(raw: Any, *, limit: int = 24) -> list[dict[str, float]]:
    if isinstance(raw, dict):
        rows = [raw]
    else:
        rows = raw if isinstance(raw, list) else []
    output: list[dict[str, float]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        x = _to_float(row.get("x"))
        y = _to_float(row.get("y"))
        width = _to_float(row.get("width"))
        height = _to_float(row.get("height"))
        if x is None or y is None or width is None or height is None:
            continue
        left = max(0.0, min(1.0, x))
        top = max(0.0, min(1.0, y))
        normalized_width = max(0.0, min(1.0 - left, width))
        normalized_height = max(0.0, min(1.0 - top, height))
        if normalized_width < 0.002 or normalized_height < 0.002:
            continue
        key = (
            round(left, 6),
            round(top, 6),
            round(normalized_width, 6),
            round(normalized_height, 6),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(
            {
                "x": key[0],
                "y": key[1],
                "width": key[2],
                "height": key[3],
            }
        )
        if len(output) >= max(1, int(limit)):
            break
    return output


def _strength_tier(score: float | None) -> int | None:
    if score is None or score <= 0:
        return None
    if score >= 0.70:
        return 3
    if score >= 0.42:
        return 2
    return 1


def _bounded_score(value: Any) -> float | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    if parsed <= 0:
        return None
    return round(max(0.0, min(1.0, parsed)), 6)


def _bounded_confidence(value: Any) -> float | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return round(max(0.0, min(1.0, parsed)), 6)


def _best_value(*rows: Any) -> Any:
    for row in rows:
        if isinstance(row, str) and row.strip():
            return row
        if row is not None and not isinstance(row, str):
            return row
    return None


def _normalize_item(*, row: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    evidence_id = _clean_text(
        _best_value(row.get("id"), row.get("evidence_id"), row.get("evidenceId")),
        max_len=80,
    ).lower() or fallback_id
    if not evidence_id.startswith("evidence-"):
        evidence_id = f"evidence-{evidence_id}"

    source_map = row.get("source") if isinstance(row.get("source"), dict) else {}
    review_map = row.get("review_location") if isinstance(row.get("review_location"), dict) else {}
    target_map = row.get("highlight_target") if isinstance(row.get("highlight_target"), dict) else {}
    quality_map = row.get("evidence_quality") if isinstance(row.get("evidence_quality"), dict) else {}
    citation_map = row.get("citation") if isinstance(row.get("citation"), dict) else {}

    source_url = _normalize_url(
        _best_value(
            row.get("source_url"),
            row.get("sourceUrl"),
            source_map.get("url"),
            review_map.get("source_url"),
            review_map.get("sourceUrl"),
            row.get("url"),
            row.get("page_url"),
        )
    )
    source_id = _clean_text(
        _best_value(
            row.get("source_id"),
            source_map.get("id"),
            review_map.get("source_id"),
            review_map.get("sourceId"),
        ),
        max_len=180,
    )
    source_name = _clean_text(
        _best_value(
            row.get("source_name"),
            row.get("source"),
            source_map.get("title"),
            source_map.get("label"),
            row.get("title"),
            f"Indexed source {fallback_id.split('-')[-1]}",
        ),
        max_len=220,
    ) or "Indexed source"
    file_id = _clean_text(
        _best_value(
            row.get("file_id"),
            row.get("fileId"),
            source_map.get("file_id"),
            source_map.get("fileId"),
            review_map.get("file_id"),
            review_map.get("fileId"),
        ),
        max_len=180,
    )
    page = _clean_text(
        _best_value(
            row.get("page"),
            source_map.get("page"),
            review_map.get("page"),
        ),
        max_len=40,
    )
    extract = _clean_text(
        _best_value(
            row.get("extract"),
            row.get("snippet"),
            citation_map.get("quote"),
            target_map.get("phrase"),
            row.get("text"),
        ),
        max_len=2000,
    )
    if not extract:
        extract = "No extract available for this citation."

    source_type = _normalize_source_type(
        source_type=_best_value(
            row.get("source_type"),
            row.get("sourceType"),
            source_map.get("type"),
            review_map.get("surface"),
        ),
        source_name=source_name,
        source_url=source_url,
        file_id=file_id,
    )
    if source_type == "web":
        file_id = ""
    if not file_id and source_id and not source_id.lower().startswith(("http://", "https://")):
        file_id = _clean_text(source_id, max_len=180)

    highlight_boxes = _normalize_highlight_boxes(
        _best_value(
            row.get("highlight_boxes"),
            row.get("highlightBoxes"),
            target_map.get("boxes"),
            row.get("region"),
        )
    )
    unit_id = _clean_text(
        _best_value(
            row.get("unit_id"),
            row.get("unitId"),
            target_map.get("unit_id"),
            target_map.get("unitId"),
        ),
        max_len=180,
    )
    match_quality = _clean_text(
        _best_value(
            row.get("match_quality"),
            row.get("matchQuality"),
            quality_map.get("match_quality"),
            quality_map.get("matchQuality"),
        ),
        max_len=40,
    ).lower()
    char_start = _to_int(
        _best_value(
            row.get("char_start"),
            row.get("charStart"),
            target_map.get("char_start"),
            target_map.get("charStart"),
        )
    )
    char_end = _to_int(
        _best_value(
            row.get("char_end"),
            row.get("charEnd"),
            target_map.get("char_end"),
            target_map.get("charEnd"),
        )
    )
    if char_start is not None and char_start <= 0:
        char_start = None
    if char_end is not None and (char_start is None or char_end <= char_start):
        char_end = None

    strength_score = _bounded_score(
        _best_value(
            row.get("strength_score"),
            row.get("strengthScore"),
            quality_map.get("score"),
            quality_map.get("strength_score"),
        )
    )
    strength_tier = _to_int(
        _best_value(
            row.get("strength_tier"),
            row.get("strengthTier"),
            quality_map.get("tier"),
            quality_map.get("strength_tier"),
        )
    )
    if strength_tier is None:
        strength_tier = _strength_tier(strength_score)
    confidence = _bounded_confidence(_best_value(row.get("confidence"), quality_map.get("confidence")))
    collected_by = _clean_text(_best_value(row.get("collected_by"), row.get("collectedBy"), "agent.research"), max_len=120)

    graph_node_ids = _normalize_ref_ids(_best_value(row.get("graph_node_ids"), row.get("graphNodeIds")))
    scene_refs = _normalize_ref_ids(_best_value(row.get("scene_refs"), row.get("sceneRefs")))
    event_refs = _normalize_ref_ids(_best_value(row.get("event_refs"), row.get("eventRefs")))
    artifact_refs = _normalize_ref_ids(_best_value(row.get("artifact_refs"), row.get("artifactRefs")))
    selector = _clean_text(
        _best_value(
            row.get("selector"),
            target_map.get("selector"),
            review_map.get("selector"),
        ),
        max_len=280,
    )
    review_surface = "web" if source_type == "web" else "pdf" if source_type == "pdf" else "file"
    citation_quote = _clean_text(_best_value(citation_map.get("quote"), target_map.get("phrase"), extract), max_len=1200)
    citation_label = _clean_text(_best_value(citation_map.get("label"), evidence_id.replace("evidence-", "")), max_len=40)

    normalized: dict[str, Any] = {
        "id": evidence_id,
        "source_type": source_type,
        "title": _clean_text(_best_value(row.get("title"), f"Evidence [{citation_label}]"), max_len=220),
        "source_name": source_name,
        "extract": extract,
        "collected_by": collected_by,
        "graph_node_ids": graph_node_ids,
        "scene_refs": scene_refs,
        "event_refs": event_refs,
        "artifact_refs": artifact_refs,
        "source": {
            "id": source_id or None,
            "type": source_type,
            "title": source_name,
            "url": source_url or None,
            "file_id": file_id or None,
            "page": page or None,
        },
        "citation": {
            "id": evidence_id,
            "label": f"[{citation_label}]",
            "quote": citation_quote,
            "source_id": source_id or None,
            "source_url": source_url or None,
        },
        "review_location": {
            "surface": review_surface,
            "source_id": source_id or None,
            "source_url": source_url or None,
            "file_id": file_id or None,
            "page": page or None,
            "selector": selector or None,
        },
        "highlight_target": {
            "boxes": highlight_boxes,
            "unit_id": unit_id or None,
            "char_start": char_start,
            "char_end": char_end,
            "selector": selector or None,
            "phrase": citation_quote,
        },
        "evidence_quality": {
            "score": strength_score,
            "tier": strength_tier,
            "confidence": confidence,
            "match_quality": match_quality or None,
        },
    }

    if source_url:
        normalized["source_url"] = source_url
    if file_id:
        normalized["file_id"] = file_id
    if page:
        normalized["page"] = page
    if source_id:
        normalized["source_id"] = source_id
    if unit_id:
        normalized["unit_id"] = unit_id
    if selector:
        normalized["selector"] = selector
    if char_start is not None:
        normalized["char_start"] = char_start
    if char_end is not None:
        normalized["char_end"] = char_end
    if match_quality:
        normalized["match_quality"] = match_quality
    if strength_score is not None:
        normalized["strength_score"] = strength_score
    if strength_tier is not None:
        normalized["strength_tier"] = strength_tier
    if confidence is not None:
        normalized["confidence"] = confidence
    if highlight_boxes:
        normalized["highlight_boxes"] = highlight_boxes
        normalized["region"] = highlight_boxes[0]
    return normalized


def normalize_verification_evidence_items(
    rows: list[dict[str, Any]],
    *,
    max_items: int = 32,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    output: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows[: max(1, int(max_items) * 4)], start=1):
        if not isinstance(row, dict):
            continue
        normalized = _normalize_item(row=row, fallback_id=f"evidence-{index}")
        evidence_id = str(normalized.get("id", "")).strip().lower()
        if not evidence_id or evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)
        output.append(normalized)
        if len(output) >= max(1, int(max_items)):
            break
    return output


__all__ = [
    "VERIFICATION_CONTRACT_VERSION",
    "normalize_verification_evidence_items",
]
