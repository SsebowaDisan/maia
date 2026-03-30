from __future__ import annotations

import html
import re
from typing import Any

from .shared import (
    CITATION_PHRASE_MAX_CHARS,
    MAIA_CITATION_ANCHOR_INDEX_ENABLED,
    MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED,
    MAIA_CITATION_STRENGTH_BADGES_ENABLED,
    _CITATION_ANCHOR_OPEN_RE,
    _CITATION_ANCHOR_RE,
    _INLINE_REF_TOKEN_RE,
    _normalize_source_url,
    _score_value,
    _serialize_evidence_units,
    _serialize_highlight_boxes,
    _strength_tier,
)


def _citation_anchor(ref: dict[str, Any]) -> str:
    ref_id = int(ref.get("id", 0) or 0)
    if ref_id <= 0:
        return ""
    file_id = str(ref.get("file_id", "") or "").strip()
    if not file_id:
        source_id = str(ref.get("source_id", "") or "").strip()
        if source_id and not source_id.lower().startswith(("http://", "https://")):
            file_id = source_id
    source_url = _normalize_source_url(ref.get("source_url"))
    page_label = str(ref.get("page_label", "") or "").strip()
    unit_id = str(ref.get("unit_id", "") or "").strip()
    selector = str(ref.get("selector", "") or "").strip()
    phrase = str(ref.get("phrase", "") or "").strip()
    match_quality = str(ref.get("match_quality", "") or "").strip()
    try:
        char_start = int(ref.get("char_start", 0) or 0) if str(ref.get("char_start", "")).strip() else 0
    except Exception:
        char_start = 0
    try:
        char_end = int(ref.get("char_end", 0) or 0) if str(ref.get("char_end", "")).strip() else 0
    except Exception:
        char_end = 0
    strength_score = _score_value(ref.get("strength_score"))
    strength_tier = _strength_tier(strength_score)
    boxes_payload = _serialize_highlight_boxes(ref.get("highlight_boxes"))
    units_payload = _serialize_evidence_units(ref.get("evidence_units"))
    attrs = [
        f"href='#evidence-{ref_id}'",
        f"id='citation-{ref_id}'",
        "class='citation'",
        f"data-citation-number='{ref_id}'",
        f"data-evidence-id='evidence-{ref_id}'",
    ]
    if file_id:
        attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if not source_url:
            viewer_url = f"/api/uploads/files/{html.escape(file_id, quote=True)}/raw"
            if page_label:
                viewer_url += f"#page={html.escape(page_label, quote=True)}"
            attrs.append(f"data-viewer-url='{viewer_url}'")
    if source_url:
        attrs.append(f"data-source-url='{html.escape(source_url, quote=True)}'")
    if page_label:
        attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
    if MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED and MAIA_CITATION_ANCHOR_INDEX_ENABLED and unit_id:
        attrs.append(f"data-unit-id='{html.escape(unit_id[:160], quote=True)}'")
    if MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED and MAIA_CITATION_ANCHOR_INDEX_ENABLED and selector:
        attrs.append(f"data-selector='{html.escape(selector[:280], quote=True)}'")
    if MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED and phrase:
        attrs.append(f"data-phrase='{html.escape(phrase[:CITATION_PHRASE_MAX_CHARS], quote=True)}'")
    if MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED and MAIA_CITATION_ANCHOR_INDEX_ENABLED and match_quality:
        attrs.append(f"data-match-quality='{html.escape(match_quality[:32], quote=True)}'")
    if MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED and MAIA_CITATION_ANCHOR_INDEX_ENABLED and char_start > 0:
        attrs.append(f"data-char-start='{char_start}'")
    if MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED and MAIA_CITATION_ANCHOR_INDEX_ENABLED and char_end > char_start:
        attrs.append(f"data-char-end='{char_end}'")
    if strength_score > 0:
        attrs.append(f"data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'")
        if MAIA_CITATION_STRENGTH_BADGES_ENABLED:
            attrs.append(f"data-strength-tier='{strength_tier}'")
    if boxes_payload:
        attrs.append(f"data-boxes='{html.escape(boxes_payload, quote=True)}'")
    if units_payload:
        attrs.append(f"data-evidence-units='{html.escape(units_payload, quote=True)}'")
    return f"<a {' '.join(attrs)}>[{ref_id}]</a>"


def _ref_id_from_anchor_open(anchor_open: str) -> int:
    evidence_attr_match = re.search(
        r"data-evidence-id=['\"]evidence-(\d{1,4})['\"]",
        anchor_open,
        flags=re.IGNORECASE,
    )
    if evidence_attr_match:
        return int(evidence_attr_match.group(1))
    href_match = re.search(
        r"href=['\"]#evidence-(\d{1,4})['\"]",
        anchor_open,
        flags=re.IGNORECASE,
    )
    if href_match:
        return int(href_match.group(1))
    id_match = re.search(
        r"id=['\"](?:citation|mark)-(\d{1,4})['\"]",
        anchor_open,
        flags=re.IGNORECASE,
    )
    if id_match:
        return int(id_match.group(1))
    number_match = re.search(
        r"data-citation-number=['\"](\d{1,4})['\"]",
        anchor_open,
        flags=re.IGNORECASE,
    )
    if number_match:
        return int(number_match.group(1))
    return 0


def _augment_existing_citation_anchors(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text or not refs:
        return text

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    if not ref_by_id:
        return text

    def replace_open(match: re.Match[str]) -> str:
        anchor_open = match.group(0)
        ref_id = _ref_id_from_anchor_open(anchor_open)
        ref = ref_by_id.get(ref_id)
        if not ref:
            return anchor_open
        normalized_open = anchor_open
        normalized_href = f"href='#evidence-{ref_id}'"
        if re.search(r"\bhref=['\"]", normalized_open, flags=re.IGNORECASE):
            normalized_open = re.sub(
                r"href=['\"][^'\"]*['\"]",
                normalized_href,
                normalized_open,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            normalized_open = f"{normalized_open[:-1]} {normalized_href}>"
        if re.search(r"\bid=['\"]mark-\d{1,4}['\"]", normalized_open, flags=re.IGNORECASE):
            normalized_open = re.sub(
                r"id=['\"]mark-\d{1,4}['\"]",
                f"id='citation-{ref_id}'",
                normalized_open,
                count=1,
                flags=re.IGNORECASE,
            )
        elif not re.search(r"\bid=['\"]citation-\d{1,4}['\"]", normalized_open, flags=re.IGNORECASE):
            normalized_open = f"{normalized_open[:-1]} id='citation-{ref_id}'>"
        if re.search(r"\bdata-evidence-id=['\"]evidence-\d{1,4}['\"]", normalized_open, flags=re.IGNORECASE):
            normalized_open = re.sub(
                r"data-evidence-id=['\"]evidence-\d{1,4}['\"]",
                f"data-evidence-id='evidence-{ref_id}'",
                normalized_open,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            normalized_open = f"{normalized_open[:-1]} data-evidence-id='evidence-{ref_id}'>"

        additions: list[str] = []
        file_id = str(ref.get("file_id", "") or "").strip()
        if not file_id:
            source_id = str(ref.get("source_id", "") or "").strip()
            if source_id and not source_id.lower().startswith(("http://", "https://")):
                file_id = source_id
        source_url = _normalize_source_url(ref.get("source_url"))
        page_label = str(ref.get("page_label", "") or "").strip()
        unit_id = str(ref.get("unit_id", "") or "").strip()
        phrase = str(ref.get("phrase", "") or "").strip()
        match_quality = str(ref.get("match_quality", "") or "").strip()
        try:
            char_start = int(ref.get("char_start", 0) or 0) if str(ref.get("char_start", "")).strip() else 0
        except Exception:
            char_start = 0
        try:
            char_end = int(ref.get("char_end", 0) or 0) if str(ref.get("char_end", "")).strip() else 0
        except Exception:
            char_end = 0
        strength_score = _score_value(ref.get("strength_score"))
        strength_tier = _strength_tier(strength_score)
        boxes_payload = _serialize_highlight_boxes(ref.get("highlight_boxes"))
        units_payload = _serialize_evidence_units(ref.get("evidence_units"))

        if file_id and not re.search(r"\bdata-file-id=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if (
            file_id
            and not source_url
            and not re.search(r"\bdata-viewer-url=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            _vurl = f"/api/uploads/files/{html.escape(file_id, quote=True)}/raw"
            if page_label:
                _vurl += f"#page={html.escape(page_label, quote=True)}"
            additions.append(f"data-viewer-url='{_vurl}'")
        if source_url and not re.search(r"\bdata-source-url=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-source-url='{html.escape(source_url, quote=True)}'")
        if page_label and not re.search(r"\bdata-page=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-page='{html.escape(page_label, quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and unit_id
            and not re.search(r"\bdata-unit-id=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            additions.append(f"data-unit-id='{html.escape(unit_id[:160], quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and phrase
            and not re.search(r"\bdata-phrase=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            additions.append(f"data-phrase='{html.escape(phrase[:CITATION_PHRASE_MAX_CHARS], quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and match_quality
            and not re.search(r"\bdata-match-quality=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            additions.append(f"data-match-quality='{html.escape(match_quality[:32], quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and char_start > 0
            and not re.search(r"\bdata-char-start=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            additions.append(f"data-char-start='{char_start}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and char_end > char_start
            and not re.search(r"\bdata-char-end=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            additions.append(f"data-char-end='{char_end}'")
        if strength_score > 0 and not re.search(r"\bdata-strength=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'")
            if MAIA_CITATION_STRENGTH_BADGES_ENABLED and not re.search(
                r"\bdata-strength-tier=['\"]", normalized_open, flags=re.IGNORECASE
            ):
                additions.append(f"data-strength-tier='{strength_tier}'")
        if boxes_payload and not re.search(r"\bdata-boxes=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-boxes='{html.escape(boxes_payload, quote=True)}'")
        if units_payload and not re.search(r"\bdata-evidence-units=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-evidence-units='{html.escape(units_payload, quote=True)}'")

        if not additions:
            return normalized_open
        return f"{normalized_open[:-1]} {' '.join(additions)}>"

    return _CITATION_ANCHOR_OPEN_RE.sub(replace_open, text)


def _anchors_to_bracket_markers(answer: str) -> str:
    text = str(answer or "")
    if not text:
        return text

    def replace_anchor(match: re.Match[str]) -> str:
        anchor_open, anchor_label, _anchor_close = match.groups()
        ref_id = _ref_id_from_anchor_open(anchor_open)
        if ref_id <= 0:
            label_match = _INLINE_REF_TOKEN_RE.search(anchor_label or "")
            if label_match:
                try:
                    ref_id = int(label_match.group(1))
                except Exception:
                    ref_id = 0
        if ref_id <= 0:
            return ""
        return f"[{ref_id}]"

    return _CITATION_ANCHOR_RE.sub(replace_anchor, text)
