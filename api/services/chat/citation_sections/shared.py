from __future__ import annotations

import html
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)

from ..constants import (
    MAIA_CITATION_ANCHOR_INDEX_ENABLED,
    MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED,
    MAIA_CITATION_STRENGTH_BADGES_ENABLED,
    MAIA_CITATION_STRENGTH_WEIGHT_LLM,
    MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL,
    MAIA_CITATION_STRENGTH_WEIGHT_SPAN,
)

CITATION_MODE_INLINE = "inline"
CITATION_MODE_FOOTNOTE = "footnote"
ALLOWED_CITATION_MODES = {"highlight", CITATION_MODE_INLINE, CITATION_MODE_FOOTNOTE}
CITATION_PHRASE_MAX_CHARS = 420
CITATION_BOXES_MAX_CHARS = 2000
EVIDENCE_UNITS_MAX_CHARS = 9000
MAX_HIGHLIGHT_BOXES = 24
_CITATION_SECTION_RE = re.compile(
    r"(^|\n)\s*##\s+(Evidence\s+Citations|Sources)\b",
    flags=re.IGNORECASE,
)
_EVIDENCE_SUFFIX_RE = re.compile(r"\n\nEvidence:\s", flags=re.IGNORECASE)
_DETAILS_BLOCK_RE = re.compile(
    r"(<details\b[^>]*>)([\s\S]*?)</details>",
    flags=re.IGNORECASE,
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_CITATION_ANCHOR_OPEN_RE = re.compile(
    r"<a\b[^>]*class=['\"][^'\"]*\bcitation\b[^'\"]*['\"][^>]*>",
    flags=re.IGNORECASE,
)
_CITATION_ANCHOR_RE = re.compile(
    r"(<a\b[^>]*class=['\"][^'\"]*\bcitation\b[^'\"]*['\"][^>]*>)([\s\S]*?)(</a>)",
    flags=re.IGNORECASE,
)
_DETAILS_BOXES_RE = re.compile(r"data-boxes=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_BBOXES_RE = re.compile(r"data-bboxes=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_STRENGTH_RE = re.compile(r"data-strength=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_UNIT_ID_RE = re.compile(r"data-unit-id=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_MATCH_QUALITY_RE = re.compile(r"data-match-quality=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_CHAR_START_RE = re.compile(r"data-char-start=['\"](\d{1,12})['\"]", flags=re.IGNORECASE)
_DETAILS_CHAR_END_RE = re.compile(r"data-char-end=['\"](\d{1,12})['\"]", flags=re.IGNORECASE)
_DETAILS_SOURCE_URL_RE = re.compile(r"data-source-url=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_EVIDENCE_UNITS_RE = re.compile(r"data-evidence-units=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._/-]{1,}")
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
_SENTENCE_SEGMENT_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")
_INLINE_REF_TOKEN_RE = re.compile(r"(?:\[|【|ã€|\{)\s*(\d{1,4})\s*(?:\]|】|ã€‘|\})")
_CITATION_LIST_ITEM_RE = re.compile(r"^\s*-\s*\[(\d{1,4})\]\s*(.+?)\s*$")
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
_URL_TOKEN_RE = re.compile(r"https?://", flags=re.IGNORECASE)
_TOP_LEVEL_MD_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.IGNORECASE | re.MULTILINE)
_CONTEXT_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "claim",
    "evidence",
    "sentence",
    "source",
    "summary",
    "note",
    "section",
    "page",
    "phrase",
    "line",
    "you",
    "your",
}
_MIN_CONTEXT_MATCH_SCORE = 0.2
_FAST_QA_NOISE_SECTION_TITLES = {
    "delivery status",
    "delivery attempt overview",
    "contract gate",
    "contract gate summary",
    "verification",
    "verification and quality assessment",
    "research execution status",
    "execution summary",
    "execution issues",
    "files and documents",
    # LLM sometimes copies agent-answer structural sections into Fast QA responses;
    # strip them here so the pipeline's own citation/next-steps sections take over.
    "evidence citations",
    "recommended next steps",
    "next steps",
    "suggested next steps",
}
_FAST_QA_NOISE_SECTION_SUBSTRINGS = (
    "delivery status",
    "delivery attempt",
    "contract gate",
    "verification and quality",
    "execution summary",
    "execution issues",
    "files and documents",
    "recommended next steps",
    "suggested next steps",
)


def _upsert_html_attr(tag: str, attr_name: str, attr_value: str) -> str:
    normalized_tag = str(tag or "")
    if not normalized_tag or not normalized_tag.endswith(">"):
        return normalized_tag
    safe_value = html.escape(str(attr_value or ""), quote=True)
    if not safe_value:
        return normalized_tag
    attr_pattern = re.compile(
        rf"\b{re.escape(attr_name)}=['\"][^'\"]*['\"]",
        flags=re.IGNORECASE,
    )
    if attr_pattern.search(normalized_tag):
        return attr_pattern.sub(f"{attr_name}='{safe_value}'", normalized_tag, count=1)
    return f"{normalized_tag[:-1]} {attr_name}='{safe_value}'>"


def _normalize_info_evidence_html(info_html: str) -> str:
    text = str(info_html or "")
    if not text or "<details" not in text.lower():
        return text

    output: list[str] = []
    cursor = 0
    seen_ref_ids: set[int] = set()
    next_ref_id = 1

    for match in _DETAILS_BLOCK_RE.finditer(text):
        tag = str(match.group(1) or "")
        body_html = str(match.group(2) or "")
        class_match = re.search(r"\bclass=['\"]([^'\"]*)['\"]", tag, flags=re.IGNORECASE)
        class_value = class_match.group(1).strip().lower() if class_match else ""
        if "evidence" not in class_value.split():
            continue

        output.append(text[cursor : match.start()])

        id_match = re.search(r"id=['\"]evidence-(\d{1,4})['\"]", tag, flags=re.IGNORECASE)
        summary_id_match = re.search(
            r"<summary[^>]*>[\s\S]*?(?:evidence\s*\[?|\[)\s*(\d{1,4})\s*\]?",
            body_html[:420],
            flags=re.IGNORECASE,
        )
        preferred_ref_id = _to_int(id_match.group(1) if id_match else "")
        if preferred_ref_id is None:
            preferred_ref_id = _to_int(summary_id_match.group(1) if summary_id_match else "")
        if preferred_ref_id is None or preferred_ref_id <= 0 or preferred_ref_id in seen_ref_ids:
            while next_ref_id in seen_ref_ids:
                next_ref_id += 1
            ref_id = next_ref_id
        else:
            ref_id = preferred_ref_id
        seen_ref_ids.add(ref_id)
        if ref_id >= next_ref_id:
            next_ref_id = ref_id + 1

        normalized_tag = _upsert_html_attr(tag, "id", f"evidence-{ref_id}")

        source_url_match = _DETAILS_SOURCE_URL_RE.search(normalized_tag)
        source_url = _normalize_source_url(
            html.unescape(source_url_match.group(1)) if source_url_match else ""
        )
        if not source_url:
            source_url = _extract_source_url_from_details_body(body_html)
        if source_url:
            normalized_tag = _upsert_html_attr(normalized_tag, "data-source-url", source_url)

        page_match = re.search(r"data-page=['\"]([^'\"]+)['\"]", normalized_tag, flags=re.IGNORECASE)
        page_value = str(page_match.group(1) if page_match else "").strip()
        if not page_value:
            summary_page_match = re.search(
                r"<summary[^>]*>[\s\S]*?page\s+(\d{1,4})[\s\S]*?</summary>",
                body_html[:420],
                flags=re.IGNORECASE,
            )
            if summary_page_match:
                normalized_tag = _upsert_html_attr(
                    normalized_tag,
                    "data-page",
                    summary_page_match.group(1).strip(),
                )

        output.append(f"{normalized_tag}{body_html}</details>")
        cursor = match.end()

    if cursor <= 0:
        return text
    output.append(text[cursor:])
    return "".join(output)


def normalize_info_evidence_html(info_html: str) -> str:
    return _normalize_info_evidence_html(info_html)


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


def _normalize_highlight_box(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    x = _to_float(raw.get("x"))
    y = _to_float(raw.get("y"))
    width = _to_float(raw.get("width"))
    height = _to_float(raw.get("height"))
    if x is None or y is None or width is None or height is None:
        return None
    left = max(0.0, min(1.0, x))
    top = max(0.0, min(1.0, y))
    normalized_width = max(0.0, min(1.0 - left, width))
    normalized_height = max(0.0, min(1.0 - top, height))
    if normalized_width < 0.002 or normalized_height < 0.002:
        return None
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "width": round(normalized_width, 6),
        "height": round(normalized_height, 6),
    }


def _normalize_highlight_boxes(raw: Any) -> list[dict[str, float]]:
    if not isinstance(raw, list):
        return []
    boxes: list[dict[str, float]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for row in raw:
        normalized = _normalize_highlight_box(row)
        if not normalized:
            continue
        key = (normalized["x"], normalized["y"], normalized["width"], normalized["height"])
        if key in seen:
            continue
        seen.add(key)
        boxes.append(normalized)
        if len(boxes) >= MAX_HIGHLIGHT_BOXES:
            break
    return boxes


def _merge_highlight_boxes(
    existing: list[dict[str, float]],
    incoming: list[dict[str, float]],
) -> list[dict[str, float]]:
    return _normalize_highlight_boxes([*existing, *incoming])


def _serialize_highlight_boxes(raw: Any) -> str:
    boxes = _normalize_highlight_boxes(raw)
    if not boxes:
        return ""
    payload = json.dumps(boxes, ensure_ascii=True, separators=(",", ":"))
    if len(payload) > CITATION_BOXES_MAX_CHARS:
        _logger.warning(
            "citation_boxes_truncated boxes=%d payload_len=%d max=%d — highlight will be missing",
            len(boxes), len(payload), CITATION_BOXES_MAX_CHARS,
        )
        # Keep the first N boxes that fit instead of dropping all
        while boxes and len(json.dumps(boxes, ensure_ascii=True, separators=(",", ":"))) > CITATION_BOXES_MAX_CHARS:
            boxes.pop()
        if boxes:
            return json.dumps(boxes, ensure_ascii=True, separators=(",", ":"))
        return ""
    return payload


def _load_highlight_boxes_attr(raw: str) -> list[dict[str, float]]:
    value = str(raw or "").strip()
    if not value:
        return []
    try:
        parsed = json.loads(html.unescape(value))
    except Exception:
        return []
    return _normalize_highlight_boxes(parsed)


def _normalize_evidence_units(raw: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _clean_text(row.get("text"))
        if len(text) < 8:
            continue
        boxes = _normalize_highlight_boxes(row.get("highlight_boxes"))
        if not boxes:
            continue
        char_start = _to_int(row.get("char_start"))
        char_end = _to_int(row.get("char_end"))
        if char_start is not None and char_start <= 0:
            char_start = None
        if char_end is not None and (char_start is None or char_end <= char_start):
            char_end = None
        key = f"{char_start or 0}|{char_end or 0}|{text[:120].lower()}"
        if key in seen:
            continue
        seen.add(key)
        item: dict[str, Any] = {
            "text": text[:240],
            "highlight_boxes": boxes,
        }
        if char_start is not None:
            item["char_start"] = char_start
        if char_end is not None:
            item["char_end"] = char_end
        output.append(item)
        if len(output) >= max(1, int(limit)):
            break
    return output


def _serialize_evidence_units(raw: Any) -> str:
    units = _normalize_evidence_units(raw)
    if not units:
        return ""
    payload = json.dumps(units, ensure_ascii=True, separators=(",", ":"))
    if len(payload) > EVIDENCE_UNITS_MAX_CHARS:
        return ""
    return payload


def _load_evidence_units_attr(raw: str) -> list[dict[str, Any]]:
    value = str(raw or "").strip()
    if not value:
        return []
    try:
        parsed = json.loads(html.unescape(value))
    except Exception:
        return []
    return _normalize_evidence_units(parsed)


def _clean_text(fragment: str) -> str:
    if not fragment:
        return ""
    without_tags = _HTML_TAG_RE.sub(" ", fragment)
    plain = html.unescape(without_tags)
    return _SPACE_RE.sub(" ", plain).strip()


def _clip_text_to_sentence_boundary(text: str, *, limit: int) -> str:
    normalized = _clean_text(text)
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[:limit]
    last_sentence = max(
        clipped.rfind(". "),
        clipped.rfind("! "),
        clipped.rfind("? "),
        clipped.rfind(".\n"),
    )
    if last_sentence >= 80:
        return clipped[: last_sentence + 1].strip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _sentence_grade_extract(
    raw: Any,
    *,
    limit: int = CITATION_PHRASE_MAX_CHARS,
    min_chars: int = 72,
    max_sentences: int = 2,
) -> str:
    text = _clean_text(str(raw or ""))
    if not text:
        return ""
    sentences = [segment.strip() for segment in _SENTENCE_SEGMENT_RE.findall(text) if segment.strip()]
    if sentences:
        selected: list[str] = []
        total_chars = 0
        for sentence in sentences:
            selected.append(sentence)
            total_chars += len(sentence)
            if total_chars >= min_chars or len(selected) >= max(1, int(max_sentences)):
                break
        candidate = " ".join(selected).strip()
        if candidate and (len(candidate) >= min_chars or len(selected) >= 2):
            return _clip_text_to_sentence_boundary(candidate, limit=limit)
    token_count = len(_TOKEN_RE.findall(text))
    if token_count >= 4 and len(text) >= 20:
        return _clip_text_to_sentence_boundary(text, limit=limit)
    return ""


def _snippet_signature_text(raw: Any, *, limit: int = 420) -> str:
    sentence_extract = _sentence_grade_extract(raw, limit=limit)
    if sentence_extract:
        return sentence_extract
    return _clip_text_to_sentence_boundary(str(raw or ""), limit=limit)


def _score_value(raw: Any) -> float:
    parsed = _to_float(raw)
    return parsed if parsed is not None else 0.0


def _normalized_retrieval_signal(snippet: dict[str, Any]) -> float:
    lexical = min(1.0, max(0.0, _score_value(snippet.get("score"))) / 25.0)
    rerank = max(0.0, _score_value(snippet.get("rerank_score")))
    vector = max(0.0, _score_value(snippet.get("vector_score")))
    return min(1.0, max(lexical, rerank, vector))


def _span_bonus(snippet: dict[str, Any]) -> float:
    exact_bonus = 0.60 if bool(snippet.get("is_exact_match", False)) else 0.0
    span_text = str(snippet.get("text", "") or "")
    sentence_grade = _sentence_grade_extract(span_text, limit=520, min_chars=72, max_sentences=2)
    raw_token_count = len(_TOKEN_RE.findall(_clean_text(span_text)))
    sentence_token_count = len(_TOKEN_RE.findall(sentence_grade))
    if sentence_grade:
        shape_bonus = min(0.40, len(sentence_grade) / 520.0)
        if sentence_token_count >= 10:
            shape_bonus = min(0.40, shape_bonus + 0.10)
    elif raw_token_count >= 8:
        shape_bonus = min(0.24, len(_clean_text(span_text)) / 1000.0)
    else:
        shape_bonus = 0.04
    return min(1.0, exact_bonus + shape_bonus)


def _evidence_text_signal(snippet: dict[str, Any]) -> float:
    span_text = _clean_text(str(snippet.get("text", "") or ""))
    if not span_text:
        return 0.0
    token_count = len(_TOKEN_RE.findall(span_text))
    sentence_grade = _sentence_grade_extract(span_text, limit=520, min_chars=72, max_sentences=2)
    if sentence_grade:
        sentence_tokens = len(_TOKEN_RE.findall(sentence_grade))
        if sentence_tokens >= 10:
            return 1.0
        if sentence_tokens >= 6:
            return 0.78
    if token_count >= 6 and len(span_text) >= 40:
        return 0.52
    if token_count >= 4 and len(span_text) >= 20:
        return 0.28
    return 0.08


def _strength_tier(value: Any) -> int:
    score = _score_value(value)
    if score >= 0.70:
        return 3
    if score >= 0.42:
        return 2
    return 1


def _snippet_strength_score(snippet: dict[str, Any]) -> float:
    retrieval = _normalized_retrieval_signal(snippet)
    llm_score = min(1.0, max(0.0, _score_value(snippet.get("llm_trulens_score"))))
    span_quality = _span_bonus(snippet)
    text_signal = _evidence_text_signal(snippet)
    weighted = (
        (retrieval * float(MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL))
        + (llm_score * float(MAIA_CITATION_STRENGTH_WEIGHT_LLM))
        + (span_quality * float(MAIA_CITATION_STRENGTH_WEIGHT_SPAN))
    )
    weighted *= (0.25 + (0.75 * text_signal))
    return round(max(0.0, min(1.0, weighted)), 6)


def _source_type_from_name(source_name: str) -> str:
    lowered = str(source_name or "").strip().lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return "url"
    if lowered.endswith(".pdf"):
        return "pdf"
    if lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg")):
        return "image"
    if lowered.endswith(".gdoc"):
        return "gdoc"
    return "file"


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
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    path_segments = [
        segment.strip().lower()
        for segment in str(parsed.path or "").split("/")
        if segment.strip()
    ]
    if len(path_segments) == 1 and path_segments[0].rstrip(":") in _ARTIFACT_URL_PATH_SEGMENTS:
        return ""
    return parsed.geturl()


def _extract_source_url_from_details_body(body_html: str) -> str:
    if not body_html:
        return ""

    href_match = re.search(
        r"<a\b[^>]*href=['\"]([^'\"]+)['\"]",
        body_html,
        flags=re.IGNORECASE,
    )
    if href_match:
        normalized = _normalize_source_url(html.unescape(href_match.group(1)))
        if normalized:
            return normalized

    link_block_match = re.search(
        r"<div[^>]*class=['\"][^'\"]*evidence-content[^'\"]*['\"][^>]*>\s*"
        r"<b>\s*Link:\s*</b>\s*([\s\S]*?)</div>",
        body_html,
        flags=re.IGNORECASE,
    )
    if not link_block_match:
        link_block_match = re.search(
            r"<div[^>]*>\s*<b>\s*Link:\s*</b>\s*([\s\S]*?)</div>",
            body_html,
            flags=re.IGNORECASE,
        )
    if not link_block_match:
        return ""

    link_text = _clean_text(link_block_match.group(1))
    if not link_text:
        return ""
    inline_url_match = re.search(r"https?://[^\s<>'\"]+", link_text, flags=re.IGNORECASE)
    if not inline_url_match:
        return ""
    return _normalize_source_url(inline_url_match.group(0).rstrip(".,;:!?"))


def _extract_phrase_from_details_body(body_html: str) -> str:
    if not body_html:
        return ""
    extract_match = re.search(
        r"<div[^>]*class=['\"][^'\"]*evidence-content[^'\"]*['\"][^>]*>\s*"
        r"<b>\s*Extract:\s*</b>\s*([\s\S]*?)</div>",
        body_html,
        flags=re.IGNORECASE,
    )
    if not extract_match:
        extract_match = re.search(
            r"<div[^>]*>\s*<b>\s*Extract:\s*</b>\s*([\s\S]*?)</div>",
            body_html,
            flags=re.IGNORECASE,
        )
    phrase = _sentence_grade_extract(extract_match.group(1) if extract_match else "")
    if not phrase:
        return ""
    return _clip_text_to_sentence_boundary(phrase, limit=CITATION_PHRASE_MAX_CHARS)


def _split_answer_for_inline_injection(answer: str) -> tuple[str, str]:
    text = str(answer or "")
    section_match = _CITATION_SECTION_RE.search(text)
    if section_match:
        return text[: section_match.start()].rstrip(), text[section_match.start() :].lstrip()
    suffix_match = _EVIDENCE_SUFFIX_RE.search(text)
    if suffix_match:
        return text[: suffix_match.start()].rstrip(), text[suffix_match.start() :].lstrip()
    return text, ""
