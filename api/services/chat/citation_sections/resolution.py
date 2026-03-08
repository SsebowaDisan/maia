from __future__ import annotations

import html
import re
from typing import Any

from .shared import (
    CITATION_PHRASE_MAX_CHARS,
    MAIA_CITATION_ANCHOR_INDEX_ENABLED,
    MAIA_CITATION_STRENGTH_BADGES_ENABLED,
    _CITATION_LIST_ITEM_RE,
    _CITATION_SECTION_RE,
    _DETAILS_BBOXES_RE,
    _DETAILS_BLOCK_RE,
    _DETAILS_BOXES_RE,
    _DETAILS_CHAR_END_RE,
    _DETAILS_CHAR_START_RE,
    _DETAILS_MATCH_QUALITY_RE,
    _DETAILS_SOURCE_URL_RE,
    _DETAILS_STRENGTH_RE,
    _DETAILS_UNIT_ID_RE,
    _clean_text,
    _load_highlight_boxes_attr,
    _normalize_info_evidence_html,
    _normalize_source_url,
    _score_value,
    _serialize_highlight_boxes,
    _snippet_signature_text,
    _strength_tier,
)


def _extract_info_refs(info_html: str) -> list[dict[str, Any]]:
    text = _normalize_info_evidence_html(str(info_html or ""))
    if not text:
        return []

    from .shared import _extract_phrase_from_details_body, _extract_source_url_from_details_body

    refs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for match in _DETAILS_BLOCK_RE.finditer(text):
        tag = match.group(1)
        body_html = match.group(2)
        id_match = re.search(r"id=['\"]evidence-(\d{1,4})['\"]", tag, flags=re.IGNORECASE)
        if not id_match:
            continue
        ref_id = int(id_match.group(1))
        if ref_id <= 0 or ref_id in seen_ids:
            continue
        seen_ids.add(ref_id)
        source_id_match = re.search(r"data-file-id=['\"]([^'\"]+)['\"]", tag, flags=re.IGNORECASE)
        page_match = re.search(r"data-page=['\"]([^'\"]+)['\"]", tag, flags=re.IGNORECASE)
        source_url_match = _DETAILS_SOURCE_URL_RE.search(tag)
        boxes_match = _DETAILS_BOXES_RE.search(tag)
        if not boxes_match:
            boxes_match = _DETAILS_BBOXES_RE.search(tag)
        strength_match = _DETAILS_STRENGTH_RE.search(tag)
        unit_id_match = _DETAILS_UNIT_ID_RE.search(tag)
        match_quality_match = _DETAILS_MATCH_QUALITY_RE.search(tag)
        char_start_match = _DETAILS_CHAR_START_RE.search(tag)
        char_end_match = _DETAILS_CHAR_END_RE.search(tag)
        if not page_match:
            summary_match = re.search(
                r"<summary[^>]*>[\s\S]*?page\s+(\d{1,4})[\s\S]*?</summary>",
                body_html[:420],
                flags=re.IGNORECASE,
            )
            page_label = summary_match.group(1).strip() if summary_match else ""
        else:
            page_label = page_match.group(1).strip()
        phrase = _extract_phrase_from_details_body(body_html)
        source_url = _normalize_source_url(
            html.unescape(source_url_match.group(1)) if source_url_match else ""
        )
        if not source_url:
            source_url = _extract_source_url_from_details_body(body_html)
        highlight_boxes = _load_highlight_boxes_attr(boxes_match.group(1) if boxes_match else "")
        refs.append(
            {
                "id": ref_id,
                "source_id": source_id_match.group(1).strip() if source_id_match else "",
                "source_url": source_url,
                "page_label": page_label,
                "label": f"Evidence {ref_id}",
                "phrase": phrase,
                "highlight_boxes": highlight_boxes,
                "unit_id": unit_id_match.group(1).strip() if unit_id_match else "",
                "match_quality": (
                    match_quality_match.group(1).strip().lower() if match_quality_match else "estimated"
                ),
                "char_start": int(char_start_match.group(1)) if char_start_match else 0,
                "char_end": int(char_end_match.group(1)) if char_end_match else 0,
                "strength_score": _score_value(strength_match.group(1) if strength_match else 0.0),
            }
        )
    refs.sort(key=lambda item: int(item.get("id", 0) or 0))
    return refs


def _extract_refs_from_answer_citation_section(answer: str) -> list[dict[str, Any]]:
    text = str(answer or "")
    if not text.strip():
        return []
    section_match = _CITATION_SECTION_RE.search(text)
    if not section_match:
        return []

    section_text = text[section_match.start() :]
    refs: list[dict[str, Any]] = []
    seen_ref_ids: set[int] = set()
    heading_seen = False
    for raw_line in section_text.splitlines():
        line = str(raw_line or "")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            if heading_seen:
                break
            heading_seen = True
            continue
        item_match = _CITATION_LIST_ITEM_RE.match(stripped)
        if not item_match:
            continue
        ref_id = int(item_match.group(1))
        if ref_id <= 0 or ref_id in seen_ref_ids:
            continue
        seen_ref_ids.add(ref_id)
        content = " ".join(str(item_match.group(2) or "").split()).strip()
        if not content:
            continue
        parts = [part.strip() for part in content.split("|") if part.strip()]
        label = parts[0] if parts else f"Evidence {ref_id}"
        source_url = _normalize_source_url(label)
        note = ""
        page_label = ""
        source_name = label
        for part in parts[1:]:
            normalized_part = " ".join(str(part or "").split()).strip()
            if not normalized_part:
                continue
            part_url = _normalize_source_url(normalized_part)
            if part_url and not source_url:
                source_url = part_url
                continue
            note_match = re.match(r"^note\s*:\s*(.+)$", normalized_part, flags=re.IGNORECASE)
            if note_match:
                note_candidate = _clean_text(note_match.group(1))
                if note_candidate:
                    note = note_candidate
                continue
            page_match = re.search(r"\bpage\s+(\d{1,4})\b", normalized_part, flags=re.IGNORECASE)
            if page_match and not page_label:
                page_label = page_match.group(1)
            lower_part = normalized_part.lower()
            if not note and lower_part not in {"internal evidence", "internal"}:
                note = _clean_text(normalized_part)
        if not source_url:
            inline_url_match = re.search(r"https?://[^\s<>'\")\]]+", content, flags=re.IGNORECASE)
            if inline_url_match:
                source_url = _normalize_source_url(inline_url_match.group(0))

        refs.append(
            {
                "id": ref_id,
                "source_id": "",
                "source_url": source_url,
                "page_label": page_label,
                "label": label,
                "source_name": source_name,
                "phrase": note[:CITATION_PHRASE_MAX_CHARS] if note else "",
                "highlight_boxes": [],
                "unit_id": "",
                "match_quality": "estimated",
                "char_start": 0,
                "char_end": 0,
                "strength_score": 0.0,
            }
        )
    refs.sort(key=lambda item: int(item.get("id", 0) or 0))
    return refs


def _merge_refs(
    primary_refs: list[dict[str, Any]],
    fallback_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not primary_refs:
        return list(fallback_refs or [])
    if not fallback_refs:
        return list(primary_refs or [])

    merged: list[dict[str, Any]] = [dict(row) for row in primary_refs if isinstance(row, dict)]
    by_id: dict[int, dict[str, Any]] = {
        int(row.get("id", 0) or 0): row
        for row in merged
        if int(row.get("id", 0) or 0) > 0
    }
    for row in fallback_refs:
        if not isinstance(row, dict):
            continue
        ref_id = int(row.get("id", 0) or 0)
        if ref_id <= 0:
            continue
        existing = by_id.get(ref_id)
        if not existing:
            copied = dict(row)
            merged.append(copied)
            by_id[ref_id] = copied
            continue
        for key in (
            "source_url",
            "page_label",
            "label",
            "source_name",
            "phrase",
            "source_id",
            "unit_id",
            "match_quality",
        ):
            current = str(existing.get(key, "") or "").strip()
            if current:
                continue
            candidate = row.get(key)
            if isinstance(candidate, str):
                cleaned = candidate.strip()
                if cleaned:
                    existing[key] = cleaned
    merged.sort(key=lambda item: int(item.get("id", 0) or 0))
    return merged


def _resolve_citation_refs(*, info_html: str, answer: str) -> list[dict[str, Any]]:
    info_refs = _extract_info_refs(info_html)
    answer_refs = _extract_refs_from_answer_citation_section(answer)
    return _merge_refs(info_refs, answer_refs)


def _compact_evidence_extract(text: str, *, max_chars: int = 520) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    clipped = cleaned[:max_chars]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped.strip()}..."


def build_fast_info_html(
    snippets_with_refs: list[dict[str, Any]],
    *,
    max_blocks: int = 6,
) -> str:
    info_blocks: list[str] = []
    rendered_refs: set[int] = set()
    for snippet in snippets_with_refs:
        ref_id = int(snippet.get("ref_id", 0) or 0)
        if ref_id > 0 and ref_id in rendered_refs:
            continue
        if ref_id > 0:
            rendered_refs.add(ref_id)

        raw_source_name = str(snippet.get("source_name", "Indexed file") or "Indexed file")
        source_name = html.escape(raw_source_name)
        source_url = _normalize_source_url(
            snippet.get("source_url")
            or snippet.get("page_url")
            or snippet.get("url")
            or (raw_source_name if raw_source_name.lower().startswith(("http://", "https://")) else "")
        )
        page_label = html.escape(str(snippet.get("page_label", "") or ""))
        excerpt = html.escape(_compact_evidence_extract(str(snippet.get("text", "") or "")))
        image_origin = snippet.get("image_origin")
        summary_label = f"Evidence [{ref_id}]" if ref_id > 0 else "Evidence"
        if page_label:
            summary_label += f" - page {page_label}"

        details_id = f" id='evidence-{ref_id}'" if ref_id > 0 else ""
        source_id = str(snippet.get("source_id", "") or "").strip()
        unit_id = str(snippet.get("unit_id", "") or "").strip()
        match_quality = str(snippet.get("match_quality", "") or "").strip().lower() or "estimated"
        try:
            char_start = int(snippet.get("char_start", 0) or 0) if str(snippet.get("char_start", "")).strip() else 0
        except Exception:
            char_start = 0
        try:
            char_end = int(snippet.get("char_end", 0) or 0) if str(snippet.get("char_end", "")).strip() else 0
        except Exception:
            char_end = 0
        details_page_attr = f" data-page='{page_label}'" if page_label else ""
        details_file_attr = f" data-file-id='{html.escape(source_id, quote=True)}'" if source_id else ""
        details_source_url_attr = f" data-source-url='{html.escape(source_url, quote=True)}'" if source_url else ""
        details_unit_attr = f" data-unit-id='{html.escape(unit_id[:160], quote=True)}'" if unit_id else ""
        details_match_quality_attr = (
            f" data-match-quality='{html.escape(match_quality[:32], quote=True)}'" if match_quality else ""
        )
        details_char_start_attr = f" data-char-start='{char_start}'" if char_start > 0 else ""
        details_char_end_attr = f" data-char-end='{char_end}'" if char_end > char_start else ""
        strength_score = _score_value(snippet.get("strength_score"))
        strength_tier = _strength_tier(strength_score)
        details_strength_attr = (
            f" data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'" if strength_score > 0 else ""
        )
        details_strength_tier_attr = (
            f" data-strength-tier='{strength_tier}'"
            if MAIA_CITATION_STRENGTH_BADGES_ENABLED and strength_score > 0
            else ""
        )
        boxes_payload = _serialize_highlight_boxes(snippet.get("highlight_boxes"))
        details_boxes_attr = f" data-boxes='{html.escape(boxes_payload, quote=True)}'" if boxes_payload else ""
        source_label = f"[{ref_id}] {source_name}" if ref_id > 0 else source_name
        link_block = ""
        if source_url:
            safe_source_url = html.escape(source_url, quote=True)
            link_block = (
                "<div class='evidence-content'><b>Link:</b> "
                f"<a href='{safe_source_url}' target='_blank' rel='noopener noreferrer'>{safe_source_url}</a>"
                "</div>"
            )
        block = (
            f"<details class='evidence'{details_id}{details_file_attr}{details_page_attr}"
            f"{details_source_url_attr}"
            f"{details_unit_attr if MAIA_CITATION_ANCHOR_INDEX_ENABLED else ''}"
            f"{details_match_quality_attr if MAIA_CITATION_ANCHOR_INDEX_ENABLED else ''}"
            f"{details_char_start_attr if MAIA_CITATION_ANCHOR_INDEX_ENABLED else ''}"
            f"{details_char_end_attr if MAIA_CITATION_ANCHOR_INDEX_ENABLED else ''}"
            f"{details_strength_attr}{details_strength_tier_attr}{details_boxes_attr} {'open' if not info_blocks else ''}>"
            f"<summary><i>{summary_label}</i></summary>"
            f"<div><b>Source:</b> {source_label}</div>"
            f"<div class='evidence-content'><b>Extract:</b> {excerpt}</div>"
            f"{link_block}"
        )
        if isinstance(image_origin, str) and image_origin.startswith("data:image/"):
            safe_src = html.escape(image_origin, quote=True)
            block += "<figure>" f"<img src=\"{safe_src}\" alt=\"evidence image\"/>" "</figure>"
        block += "</details>"
        info_blocks.append(block)
        if len(info_blocks) >= max_blocks:
            break
    return "".join(info_blocks)
