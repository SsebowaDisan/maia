from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import urlparse

from .evidence_items import EvidenceItem, EvidenceRegion, infer_evidence_source_type

_ARTIFACT_URL_PATH_SEGMENTS = {
    "extract",
    "source",
    "link",
    "evidence",
    "citation",
    "title",
    "markdown",
    "content",
    "published",
    "time",
    "url",
}


def _source_metadata(source: Any) -> dict[str, Any]:
    payload = getattr(source, "metadata", {})
    return payload if isinstance(payload, dict) else {}


def _source_page_label(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("page_label", "page", "page_number", "page_index"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:24]
    return ""


def _compact_text(value: str, *, max_chars: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    clipped = text[:max_chars]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped.strip()}..."


def _normalize_source_url(raw_value: Any) -> str:
    value = " ".join(str(raw_value or "").split()).strip()
    if not value:
        return ""
    if len(value) > 2048:
        value = value[:2048]
    value = value.strip(" <>\"'`")
    value = value.rstrip(".,;:!?")
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path_segments = [
        segment.strip().lower()
        for segment in str(parsed.path or "").split("/")
        if segment.strip()
    ]
    if len(path_segments) == 1 and path_segments[0].rstrip(":") in _ARTIFACT_URL_PATH_SEGMENTS:
        return ""
    return parsed.geturl()


def _clean_source_label(raw_value: Any) -> str:
    text = " ".join(str(raw_value or "").split()).strip()
    if not text:
        return ""
    text = re.sub(r"\bURL\s*Source\s*:\s*https?://[^\s<>'\")\]]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPublished\s*Time\s*:\s*[^|]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMarkdown\s*Content\s*:\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" |:-")
    return _compact_text(text, max_chars=180)


def _source_extract(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("extract", "excerpt", "snippet", "quote", "text_excerpt", "text"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return _compact_text(value, max_chars=1200)
    source_label = _clean_source_label(getattr(source, "label", ""))
    source_type = str(getattr(source, "source_type", "") or "").strip().lower()
    if source_label and source_type in {"file", "document", "pdf"}:
        return _compact_text(source_label, max_chars=260)
    return ""


def _source_url(source: Any) -> str:
    metadata = _source_metadata(source)
    label = " ".join(str(getattr(source, "label", "") or "").split()).strip()
    url_candidates = [
        getattr(source, "url", ""),
        metadata.get("source_url"),
        metadata.get("page_url"),
        metadata.get("url"),
        metadata.get("link"),
        label if label.lower().startswith(("http://", "https://")) else "",
    ]
    for candidate in url_candidates:
        normalized = _normalize_source_url(candidate)
        if normalized:
            return normalized
    return ""


def _source_display_label(source: Any, *, source_url: str, fallback_id: int) -> str:
    label = _clean_source_label(getattr(source, "label", ""))
    if label and not label.lower().startswith(("http://", "https://")):
        return label
    if source_url:
        return source_url
    return f"Indexed source {fallback_id}"


def _source_match_quality(source: Any) -> str:
    metadata = _source_metadata(source)
    raw = " ".join(str(metadata.get("match_quality") or "").split()).strip().lower()
    if not raw:
        return ""
    return raw[:32]


def _source_unit_id(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("unit_id", "chunk_id", "span_id"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:160]
    return ""


def _source_char_span(source: Any) -> tuple[int, int]:
    metadata = _source_metadata(source)
    try:
        char_start = int(metadata.get("char_start", 0) or 0)
    except Exception:
        char_start = 0
    try:
        char_end = int(metadata.get("char_end", 0) or 0)
    except Exception:
        char_end = 0
    if char_start <= 0 or char_end <= char_start:
        return 0, 0
    return char_start, char_end


def _source_strength_score(source: Any) -> float:
    metadata = _source_metadata(source)
    for key in ("strength_score", "score"):
        try:
            value = float(metadata.get(key, 0.0) or 0.0)
        except Exception:
            continue
        if value > 0:
            return max(0.0, min(1.0, value))
    return 0.0


def _source_file_id(source: Any) -> str:
    direct = " ".join(str(getattr(source, "file_id", "") or "").split()).strip()
    if direct:
        return direct
    metadata = _source_metadata(source)
    for key in ("file_id", "source_id"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value
    return ""


def _source_highlight_boxes(source: Any) -> list[dict[str, float]]:
    metadata = _source_metadata(source)
    raw = metadata.get("highlight_boxes")
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, float]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x", 0.0))
            y = float(item.get("y", 0.0))
            width = float(item.get("width", 0.0))
            height = float(item.get("height", 0.0))
        except Exception:
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
        normalized.append(
            {
                "x": key[0],
                "y": key[1],
                "width": key[2],
                "height": key[3],
            }
        )
        if len(normalized) >= 24:
            break
    return normalized


def _source_confidence(source: Any) -> float | None:
    metadata = _source_metadata(source)
    return EvidenceItem.confidence_from(metadata.get("confidence"), getattr(source, "score", None))


def _source_collected_by(source: Any) -> str:
    metadata = _source_metadata(source)
    for key in ("collected_by", "agent_id", "agent_role", "owner_role"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:120]
    return "agent.research"


def _source_ref_ids(source: Any, *keys: str) -> list[str]:
    metadata = _source_metadata(source)
    return EvidenceItem.refs_from_metadata(metadata, *keys)


def _strength_tier_from_score(strength_score: float) -> int:
    if strength_score >= 0.7:
        return 3
    if strength_score >= 0.42:
        return 2
    return 1


def _build_evidence_items_from_sources(response_sources: list[Any]) -> list[EvidenceItem]:
    evidence_items: list[EvidenceItem] = []
    for idx, source in enumerate(response_sources, start=1):
        source_url = _source_url(source)
        source_name = _source_display_label(source, source_url=source_url, fallback_id=idx)
        page_label = _source_page_label(source)
        source_extract = _source_extract(source)
        file_id = _source_file_id(source)
        source_boxes = _source_highlight_boxes(source)
        source_unit_id = _source_unit_id(source)
        source_match_quality = _source_match_quality(source)
        char_start, char_end = _source_char_span(source)
        strength_score = _source_strength_score(source)
        strength_tier = _strength_tier_from_score(strength_score) if strength_score > 0 else 0

        highlight_boxes: list[EvidenceRegion] = []
        for box in source_boxes:
            region = EvidenceRegion.from_payload(box)
            if region is None:
                continue
            highlight_boxes.append(region)
            if len(highlight_boxes) >= 24:
                break

        title = f"Evidence [{idx}]"
        if page_label:
            title += f" - page {page_label}"

        evidence_items.append(
            EvidenceItem(
                evidence_id=f"evidence-{idx}",
                source_type=infer_evidence_source_type(
                    source_type=str(getattr(source, "source_type", "") or ""),
                    source_url=source_url,
                    file_id=file_id,
                ),
                title=title,
                source_name=source_name,
                source_url=source_url or None,
                file_id=file_id or None,
                page=page_label or None,
                extract=source_extract,
                unit_id=source_unit_id or None,
                char_start=char_start if char_start > 0 else None,
                char_end=char_end if char_end > char_start else None,
                match_quality=source_match_quality or None,
                strength_score=round(strength_score, 6) if strength_score > 0 else None,
                strength_tier=strength_tier if strength_tier > 0 else None,
                confidence=_source_confidence(source),
                collected_by=_source_collected_by(source),
                highlight_boxes=highlight_boxes,
                graph_node_ids=_source_ref_ids(source, "graph_node_ids", "graph_node_id"),
                scene_refs=_source_ref_ids(source, "scene_refs", "scene_ref"),
                event_refs=_source_ref_ids(source, "event_refs", "event_id"),
                artifact_refs=_source_ref_ids(source, "artifact_refs", "artifact_id"),
            )
        )
    return evidence_items


def _build_info_html_from_sources(
    response_sources: list[Any],
    *,
    evidence_items: list[EvidenceItem] | None = None,
) -> str:
    if not response_sources:
        return ""
    rows = list(evidence_items or _build_evidence_items_from_sources(response_sources))
    if not rows:
        return ""
    info_blocks: list[str] = ["<div class='evidence-list' data-layout='kotaemon'>"]
    for idx, item in enumerate(rows, start=1):
        evidence_id = " ".join(str(item.evidence_id or "").split()).strip() or f"evidence-{idx}"
        summary_label = " ".join(str(item.title or "").split()).strip() or f"Evidence [{idx}]"
        source_url = " ".join(str(item.source_url or "").split()).strip()
        source_label = " ".join(str(item.source_name or "").split()).strip() or f"Indexed source {idx}"
        file_id = " ".join(str(item.file_id or "").split()).strip()
        page_label = " ".join(str(item.page or "").split()).strip()
        source_extract = " ".join(str(item.extract or "").split()).strip()
        source_unit_id = " ".join(str(item.unit_id or "").split()).strip()
        source_match_quality = " ".join(str(item.match_quality or "").split()).strip()
        char_start = int(item.char_start or 0)
        char_end = int(item.char_end or 0)
        strength_score = float(item.strength_score or 0.0)
        strength_tier = int(item.strength_tier or 0)
        confidence = float(item.confidence) if item.confidence is not None else None
        source_type = " ".join(str(item.source_type or "").split()).strip().lower()
        collected_by = " ".join(str(item.collected_by or "").split()).strip()
        graph_node_ids = [str(value).strip() for value in list(item.graph_node_ids or []) if str(value).strip()]
        scene_refs = [str(value).strip() for value in list(item.scene_refs or []) if str(value).strip()]
        event_refs = [str(value).strip() for value in list(item.event_refs or []) if str(value).strip()]
        source_boxes = [box.model_dump(mode="json") for box in list(item.highlight_boxes or [])]

        details_attrs = [f"class='evidence'", f"id='{html.escape(evidence_id, quote=True)}'"]
        details_attrs.append(f"data-evidence-id='{html.escape(evidence_id, quote=True)}'")
        if file_id:
            details_attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if page_label:
            details_attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
        if source_url:
            details_attrs.append(f"data-source-url='{html.escape(source_url, quote=True)}'")
        if source_unit_id:
            details_attrs.append(f"data-unit-id='{html.escape(source_unit_id, quote=True)}'")
        if source_match_quality:
            details_attrs.append(f"data-match-quality='{html.escape(source_match_quality, quote=True)}'")
        if char_start > 0:
            details_attrs.append(f"data-char-start='{char_start}'")
        if char_end > char_start:
            details_attrs.append(f"data-char-end='{char_end}'")
        if strength_score > 0:
            details_attrs.append(f"data-strength='{strength_score:.6f}'")
            details_attrs.append(f"data-strength-tier='{strength_tier or _strength_tier_from_score(strength_score)}'")
        if confidence is not None:
            details_attrs.append(f"data-confidence='{confidence:.6f}'")
        if source_type:
            details_attrs.append(f"data-source-type='{html.escape(source_type, quote=True)}'")
        if collected_by:
            details_attrs.append(f"data-collected-by='{html.escape(collected_by, quote=True)}'")
        if graph_node_ids:
            details_attrs.append(f"data-graph-node-id='{html.escape(graph_node_ids[0], quote=True)}'")
        if scene_refs:
            details_attrs.append(f"data-scene-ref='{html.escape(scene_refs[0], quote=True)}'")
        if event_refs:
            details_attrs.append(f"data-event-ref='{html.escape(event_refs[0], quote=True)}'")
        if source_boxes:
            details_attrs.append(
                "data-boxes='"
                + html.escape(
                    json.dumps(source_boxes, separators=(",", ":"), ensure_ascii=True),
                    quote=True,
                )
                + "'"
            )
        if idx == 1:
            details_attrs.append("open")

        if source_url:
            source_label_block = (
                f"<a href='{html.escape(source_url, quote=True)}' target='_blank' rel='noopener noreferrer'>"
                f"{html.escape(source_label)}"
                "</a>"
            )
            link_block = (
                "<div class='evidence-content'><b>Link:</b> "
                f"<a href='{html.escape(source_url, quote=True)}' target='_blank' rel='noopener noreferrer'>"
                f"{html.escape(source_url)}"
                "</a></div>"
            )
        else:
            source_label_block = html.escape(source_label)
            link_block = ""

        extract_block = (
            f"<div class='evidence-content'><b>Extract:</b> {html.escape(source_extract)}</div>"
            if source_extract
            else ""
        )
        info_block = (
            f"<details {' '.join(details_attrs)}>"
            f"<summary>{html.escape(summary_label)}</summary>"
            f"<div><b>Source:</b> [{idx}] {source_label_block}</div>"
            f"{extract_block}"
            f"{link_block}"
            "</details>"
        )
        info_blocks.append(info_block)
    info_blocks.append("</div>")
    return "".join(info_blocks)
