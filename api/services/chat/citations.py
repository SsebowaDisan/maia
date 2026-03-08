from __future__ import annotations

import html
import json
import re
from itertools import combinations
from typing import Any
from urllib.parse import urlparse

from .constants import (
    MAIA_CITATION_ANCHOR_INDEX_ENABLED,
    MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED,
    MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED,
    MAIA_CITATION_STRENGTH_BADGES_ENABLED,
    MAIA_CITATION_STRENGTH_ORDERING_ENABLED,
    MAIA_CITATION_STRENGTH_WEIGHT_LLM,
    MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL,
    MAIA_CITATION_STRENGTH_WEIGHT_SPAN,
    MAIA_CITATION_UNIFIED_REFS_ENABLED,
    MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
)

CITATION_MODE_INLINE = "inline"
CITATION_MODE_FOOTNOTE = "footnote"
ALLOWED_CITATION_MODES = {"highlight", CITATION_MODE_INLINE, CITATION_MODE_FOOTNOTE}
CITATION_PHRASE_MAX_CHARS = 260
CITATION_BOXES_MAX_CHARS = 2000
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
}
_FAST_QA_NOISE_SECTION_SUBSTRINGS = (
    "delivery status",
    "delivery attempt",
    "contract gate",
    "verification and quality",
    "execution summary",
    "execution issues",
    "files and documents",
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
    if parsed != parsed:  # NaN
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


def _snippet_signature_text(raw: Any, *, limit: int = 260) -> str:
    text = _clean_text(str(raw or ""))
    if not text:
        return ""
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _score_value(raw: Any) -> float:
    parsed = _to_float(raw)
    return parsed if parsed is not None else 0.0


def _normalized_retrieval_signal(snippet: dict[str, Any]) -> float:
    # Fast QA retrieval `score` is an unbounded rank-like score; normalize into [0, 1].
    lexical = min(1.0, max(0.0, _score_value(snippet.get("score"))) / 25.0)
    rerank = max(0.0, _score_value(snippet.get("rerank_score")))
    vector = max(0.0, _score_value(snippet.get("vector_score")))
    return min(1.0, max(lexical, rerank, vector))


def _span_bonus(snippet: dict[str, Any]) -> float:
    exact_bonus = 0.60 if bool(snippet.get("is_exact_match", False)) else 0.0
    span_text = str(snippet.get("text", "") or "")
    length_bonus = min(0.40, len(span_text) / 900.0)
    return min(1.0, exact_bonus + length_bonus)


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
    weighted = (
        (retrieval * float(MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL))
        + (llm_score * float(MAIA_CITATION_STRENGTH_WEIGHT_LLM))
        + (span_quality * float(MAIA_CITATION_STRENGTH_WEIGHT_SPAN))
    )
    # Keep bounded for stable UI ordering and badge tiers.
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


def _tokens(text: str) -> set[str]:
    normalized = _clean_text(text).lower()
    if not normalized:
        return set()
    values: set[str] = set()
    for raw_token in _TOKEN_RE.findall(normalized):
        token = raw_token.strip("._/-")
        if len(token) < 2:
            continue
        if token in _CONTEXT_TOKEN_STOPWORDS:
            continue
        if token.isdigit() and len(token) < 4:
            continue
        values.add(token)
    return values


def _is_informative_token(token: str) -> bool:
    candidate = str(token or "").strip().lower()
    if not candidate or candidate in _CONTEXT_TOKEN_STOPWORDS:
        return False
    if any(char.isdigit() for char in candidate):
        return True
    if any(char in "._/-" for char in candidate):
        return True
    return len(candidate) >= 6


def _context_window(text: str, pivot_index: int, *, radius: int = 220) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    start = max(0, pivot_index - radius)
    end = min(len(raw), pivot_index + radius)
    left_break = raw.rfind("\n", start, pivot_index)
    if left_break >= 0:
        start = left_break + 1
    else:
        sentence_break = max(
            raw.rfind(".", start, pivot_index),
            raw.rfind("!", start, pivot_index),
            raw.rfind("?", start, pivot_index),
        )
        if sentence_break >= 0:
            start = sentence_break + 1
    right_break = raw.find("\n", pivot_index, end)
    if right_break >= 0:
        end = right_break
    else:
        sentence_end_candidates = [
            idx for idx in (
                raw.find(".", pivot_index, end),
                raw.find("!", pivot_index, end),
                raw.find("?", pivot_index, end),
            ) if idx >= 0
        ]
        if sentence_end_candidates:
            end = min(sentence_end_candidates) + 1
    return _clean_text(raw[start:end])


def _best_ref_for_context(
    context: str,
    refs: list[dict[str, Any]],
) -> tuple[int | None, float]:
    context_tokens = _tokens(context)
    if not context_tokens:
        return None, 0.0
    best_ref_id: int | None = None
    best_score = 0.0
    for ref in refs:
        ref_id = int(ref.get("id", 0) or 0)
        if ref_id <= 0:
            continue
        phrase = str(ref.get("phrase", "") or "")
        label = str(ref.get("label", "") or "")
        source_name = str(ref.get("source_name", "") or "")
        ref_tokens = _tokens(f"{phrase} {label} {source_name}")
        if not ref_tokens:
            continue
        overlap_tokens = context_tokens & ref_tokens
        overlap = len(overlap_tokens)
        if overlap <= 0:
            continue
        informative_overlap = sum(1 for token in overlap_tokens if _is_informative_token(token))
        if overlap < 2 and informative_overlap <= 0:
            short_context_match = (
                len(context_tokens) <= 2
                and len(ref_tokens) <= 8
                and any(len(token) >= 4 for token in overlap_tokens)
            )
            if not short_context_match:
                continue
        precision = overlap / max(1, len(context_tokens))
        recall = overlap / max(1, len(ref_tokens))
        # Favor excerpts that cover the local claim with minimal noise.
        score = (precision * 0.6) + (recall * 0.3)
        if informative_overlap > 0:
            score += 0.1 * min(1.0, informative_overlap / max(1, overlap))
        if score > best_score:
            best_score = score
            best_ref_id = ref_id
    if best_score < _MIN_CONTEXT_MATCH_SCORE:
        return None, best_score
    return best_ref_id, best_score


def _is_claim_like_fragment(fragment: str) -> bool:
    text = _clean_text(fragment)
    if not text:
        return False
    normalized = text.strip()
    if len(normalized) < 20:
        return False
    if normalized.endswith(":"):
        return False
    lower = normalized.lower()
    if lower.startswith(("evidence:", "sources:", "source:")):
        return False
    # Skip likely markdown table rows.
    if "|" in fragment and fragment.count("|") >= 2:
        return False
    # Skip lines that are mostly separators.
    if re.fullmatch(r"[-=*#\s]+", normalized):
        return False
    trimmed = re.sub(r"^[-*â€¢\d\.\)\(\s]+", "", normalized)
    if len(trimmed) < 16:
        return False
    return True


def _inject_claim_citations_in_line(
    line: str,
    refs: list[dict[str, Any]],
) -> str:
    if not line or not refs:
        return line

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    if not ref_by_id:
        return line

    # Inline code fragments frequently include dotted identifiers (for example
    # `mailer.report_send`) that should not be split by sentence-level injection.
    if "`" in line:
        already_cited = bool(
            re.search(r"(?:\[|【|\{)\s*\d{1,3}\s*(?:\]|】|\})", line)
            or "class='citation'" in line
            or 'class="citation"' in line
        )
        if already_cited:
            return line
        context_without_code = _clean_text(line.replace("`", " "))
        if not _is_claim_like_fragment(line) or not context_without_code:
            return line
        best_ref_id, _score = _best_ref_for_context(context_without_code, refs)
        if best_ref_id is None or best_ref_id not in ref_by_id:
            return line
        line_stripped = line.rstrip()
        marker = f"[{best_ref_id}]"
        return f"{line_stripped} {marker}{line[len(line_stripped):]}"

    # URL/link lines should receive citation markers only at the end so markdown
    # links remain valid (no split at dots inside URLs).
    if _URL_TOKEN_RE.search(line) or _MARKDOWN_LINK_RE.search(line):
        url_line_already_cited = bool(
            re.search(r"(?:\[|【|\{)\s*\d{1,3}\s*(?:\]|】|\})", line)
            or "class='citation'" in line
            or 'class="citation"' in line
        )
        if url_line_already_cited:
            return line
        cleaned_line = _clean_text(line)
        if not _is_claim_like_fragment(line) or not cleaned_line:
            return line
        best_ref_id, _score = _best_ref_for_context(cleaned_line, refs)
        if best_ref_id is None or best_ref_id not in ref_by_id:
            return line
        ref_id = best_ref_id
        marker = f"[{ref_id}]"
        line_stripped = line.rstrip()
        return f"{line_stripped} {marker}{line[len(line_stripped):]}"

    original_line = line
    had_inline_markers = bool(_INLINE_REF_TOKEN_RE.search(line))
    had_anchor_markers = "class='citation'" in line or 'class="citation"' in line
    working_line = line
    if had_inline_markers and not had_anchor_markers:
        working_line = _INLINE_REF_TOKEN_RE.sub("", line)

    rebuilt: list[str] = []
    cursor = 0
    inserted_markers = 0
    for match in _SENTENCE_SEGMENT_RE.finditer(working_line):
        start, end = match.span()
        rebuilt.append(working_line[cursor:start])
        segment = working_line[start:end]
        cleaned = _clean_text(segment)
        should_cite = _is_claim_like_fragment(segment)
        segment_already_cited = bool(
            re.search(r"(?:\[|【|\{)\s*\d{1,3}\s*(?:\]|】|\})", segment)
            or "class='citation'" in segment
            or 'class="citation"' in segment
        )
        if should_cite and not segment_already_cited and cleaned:
            best_ref_id, _score = _best_ref_for_context(cleaned, refs)
            if best_ref_id is None or best_ref_id not in ref_by_id:
                rebuilt.append(segment)
                cursor = end
                continue
            ref_id = best_ref_id
            marker = f"[{ref_id}]"
            segment_stripped = segment.rstrip()
            segment = f"{segment_stripped} {marker}{segment[len(segment_stripped):]}"
            inserted_markers += 1
        rebuilt.append(segment)
        cursor = end
    rebuilt.append(working_line[cursor:])
    rewritten_line = "".join(rebuilt)
    if had_inline_markers and inserted_markers <= 0:
        return original_line
    return rewritten_line


def _inject_claim_level_bracket_citations(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text.strip() or not refs:
        return text

    # Avoid touching pre-rendered HTML answer bodies.
    if "class='citation'" in text or 'class="citation"' in text:
        return text

    body, tail = _split_answer_for_inline_injection(text)
    lines = body.splitlines()
    out_lines: list[str] = []
    in_code_fence = False

    for row in lines:
        stripped = row.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            out_lines.append(row)
            continue
        if in_code_fence:
            out_lines.append(row)
            continue
        if not stripped:
            out_lines.append(row)
            continue
        if stripped.startswith("#"):
            out_lines.append(row)
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            out_lines.append(row)
            continue
        out_lines.append(_inject_claim_citations_in_line(row, refs))

    rewritten_body = "\n".join(out_lines)
    if tail:
        return f"{rewritten_body.rstrip()}\n\n{tail.lstrip()}"
    return rewritten_body


def _realign_bracket_ref_numbers(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text or not refs:
        return text
    if "class='citation'" in text or 'class="citation"' in text:
        return text

    body, tail = _split_answer_for_inline_injection(text)
    if not _INLINE_REF_TOKEN_RE.search(body):
        return text

    valid_ref_ids = sorted({int(ref.get("id", 0) or 0) for ref in refs if int(ref.get("id", 0) or 0) > 0})
    if not valid_ref_ids:
        return text
    max_ref = valid_ref_ids[-1]
    min_ref = valid_ref_ids[0]
    has_in_range_marker = any(
        min_ref <= int(marker.group(1)) <= max_ref
        for marker in _INLINE_REF_TOKEN_RE.finditer(body)
    )

    def nearest_valid_ref_id(value: int) -> int:
        return min(valid_ref_ids, key=lambda ref_id: (abs(ref_id - value), ref_id))

    def replace_ref(match: re.Match[str]) -> str:
        original_ref = int(match.group(1))
        context = _context_window(body, match.start())
        best_ref_id, score = _best_ref_for_context(context, refs)
        if original_ref < 1 or original_ref > max_ref:
            if has_in_range_marker:
                return ""
            if best_ref_id is not None and score >= 0.08:
                return f"[{best_ref_id}]"
            if original_ref >= 1:
                return f"[{nearest_valid_ref_id(original_ref)}]"
            return f"[{min_ref}]"
        # Require a minimum confidence before overriding the model's numeric ref.
        if best_ref_id is None or score < 0.16:
            return match.group(0)
        return f"[{best_ref_id}]"

    realigned_body = _INLINE_REF_TOKEN_RE.sub(replace_ref, body)
    if tail:
        return f"{realigned_body.rstrip()}\n\n{tail.lstrip()}"
    return realigned_body


def _citation_anchor(ref: dict[str, Any]) -> str:
    ref_id = int(ref.get("id", 0) or 0)
    if ref_id <= 0:
        return ""
    file_id = str(ref.get("source_id", "") or "").strip()
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
    attrs = [
        f"href='#evidence-{ref_id}'",
        f"id='citation-{ref_id}'",
        "class='citation'",
        f"data-evidence-id='evidence-{ref_id}'",
    ]
    if file_id:
        attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
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
    return f"<a {' '.join(attrs)}>[{ref_id}]</a>"


def _clean_text(fragment: str) -> str:
    if not fragment:
        return ""
    without_tags = _HTML_TAG_RE.sub(" ", fragment)
    plain = html.unescape(without_tags)
    return _SPACE_RE.sub(" ", plain).strip()


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
    phrase = _clean_text(extract_match.group(1) if extract_match else "")
    if not phrase:
        return ""
    if len(phrase) <= CITATION_PHRASE_MAX_CHARS:
        return phrase
    clipped = phrase[:CITATION_PHRASE_MAX_CHARS]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def _split_answer_for_inline_injection(answer: str) -> tuple[str, str]:
    text = str(answer or "")
    section_match = _CITATION_SECTION_RE.search(text)
    if section_match:
        return text[: section_match.start()].rstrip(), text[section_match.start() :].lstrip()
    suffix_match = _EVIDENCE_SUFFIX_RE.search(text)
    if suffix_match:
        return text[: suffix_match.start()].rstrip(), text[suffix_match.start() :].lstrip()
    return text, ""


def _has_inline_citation_markers(answer: str) -> bool:
    body, _ = _split_answer_for_inline_injection(answer)
    text = str(body or "")
    if not text.strip():
        return False
    return bool(
        "class='citation'" in text
        or 'class="citation"' in text
        or _INLINE_REF_TOKEN_RE.search(text)
    )


def _inject_inline_citations(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text.strip() or not refs:
        return text
    if _has_inline_citation_markers(text):
        return text

    body, tail = _split_answer_for_inline_injection(text)
    lines = body.splitlines()
    ref_limit = max(1, min(len(refs), 2))
    injected = 0
    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    injected_ref_ids: set[int] = set()

    for index, row in enumerate(lines):
        stripped = row.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "-", "*", ">", "|")):
            continue
        if re.match(r"^\d+\.\s+", stripped):
            continue
        if stripped.startswith("<"):
            continue
        if len(stripped) < 18:
            continue
        best_ref_id, _score = _best_ref_for_context(stripped, refs)
        if best_ref_id is None:
            continue
        if best_ref_id in injected_ref_ids and len(ref_by_id) > 1:
            continue
        ref = ref_by_id.get(best_ref_id)
        if not ref:
            continue
        anchor = _citation_anchor(ref)
        if not anchor:
            continue
        lines[index] = f"{row.rstrip()} {anchor}"
        injected += 1
        injected_ref_ids.add(best_ref_id)
        if injected >= ref_limit:
            break

    if injected > 0:
        body = "\n".join(lines)
    elif body.strip() and len(refs) == 1:
        first_anchor = _citation_anchor(refs[0])
        if first_anchor:
            body = f"{body.rstrip()} {first_anchor}"

    if tail:
        return f"{body.rstrip()}\n\n{tail.lstrip()}"
    return body


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
        file_id = str(ref.get("source_id", "") or "").strip()
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

        if file_id and not re.search(r"\bdata-file-id=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if source_url and not re.search(r"\bdata-source-url=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-source-url='{html.escape(source_url, quote=True)}'")
        if page_label and not re.search(r"\bdata-page=['\"]", normalized_open, flags=re.IGNORECASE):
            additions.append(f"data-page='{html.escape(page_label, quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and unit_id
            and not re.search(
            r"\bdata-unit-id=['\"]", normalized_open, flags=re.IGNORECASE
            )
        ):
            additions.append(f"data-unit-id='{html.escape(unit_id[:160], quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and phrase
            and not re.search(r"\bdata-phrase=['\"]", normalized_open, flags=re.IGNORECASE)
        ):
            additions.append(
                f"data-phrase='{html.escape(phrase[:CITATION_PHRASE_MAX_CHARS], quote=True)}'"
            )
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and match_quality
            and not re.search(
            r"\bdata-match-quality=['\"]", normalized_open, flags=re.IGNORECASE
            )
        ):
            additions.append(f"data-match-quality='{html.escape(match_quality[:32], quote=True)}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and char_start > 0
            and not re.search(
            r"\bdata-char-start=['\"]", normalized_open, flags=re.IGNORECASE
            )
        ):
            additions.append(f"data-char-start='{char_start}'")
        if (
            MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED
            and MAIA_CITATION_ANCHOR_INDEX_ENABLED
            and char_end > char_start
            and not re.search(
            r"\bdata-char-end=['\"]", normalized_open, flags=re.IGNORECASE
            )
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


def _normalize_visible_inline_citations(answer: str) -> str:
    text = str(answer or "")
    if not text:
        return text

    ref_to_display: dict[int, int] = {}
    next_display_id = 1
    last_emitted_ref_id: int | None = None
    last_anchor_end = -1
    duplicate_gap_re = re.compile(r"^[\s,;:.!?()\[\]\-_/]*$")

    def replace_anchor(match: re.Match[str]) -> str:
        nonlocal next_display_id, last_emitted_ref_id, last_anchor_end
        anchor_open, _anchor_label, anchor_close = match.groups()
        ref_id = _ref_id_from_anchor_open(anchor_open)
        if ref_id <= 0:
            return match.group(0)

        display_id = ref_to_display.get(ref_id)
        if display_id is None:
            display_id = next_display_id
            ref_to_display[ref_id] = display_id
            next_display_id = display_id + 1

        between = text[last_anchor_end : match.start()] if last_anchor_end >= 0 else ""
        if last_emitted_ref_id == ref_id and duplicate_gap_re.fullmatch(between or ""):
            last_anchor_end = match.end()
            return ""

        if re.search(r"\bdata-citation-number=['\"]\d{1,4}['\"]", anchor_open, flags=re.IGNORECASE):
            anchor_open = re.sub(
                r"data-citation-number=['\"]\d{1,4}['\"]",
                f"data-citation-number='{display_id}'",
                anchor_open,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            anchor_open = f"{anchor_open[:-1]} data-citation-number='{display_id}'>"
        if re.search(r"\bdata-evidence-id=['\"]evidence-\d{1,4}['\"]", anchor_open, flags=re.IGNORECASE):
            anchor_open = re.sub(
                r"data-evidence-id=['\"]evidence-\d{1,4}['\"]",
                f"data-evidence-id='evidence-{ref_id}'",
                anchor_open,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            anchor_open = f"{anchor_open[:-1]} data-evidence-id='evidence-{ref_id}'>"
        last_emitted_ref_id = ref_id
        last_anchor_end = match.end()
        return f"{anchor_open}[{display_id}]{anchor_close}"

    normalized = _CITATION_ANCHOR_RE.sub(replace_anchor, text)
    if normalized == text:
        return text

    # Remove raw citation markers that remain outside anchor tags (for example stale [4]).
    rebuilt: list[str] = []
    cursor = 0
    for match in _CITATION_ANCHOR_RE.finditer(normalized):
        outside = normalized[cursor : match.start()]
        outside = re.sub(r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})", "", outside)
        rebuilt.append(outside)
        rebuilt.append(match.group(0))
        cursor = match.end()
    tail = normalized[cursor:]
    tail = re.sub(r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})", "", tail)
    rebuilt.append(tail)
    normalized = "".join(rebuilt)

    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"\(\s*\)", "", normalized)
    return normalized


def _count_citation_anchors(text: str) -> int:
    return len(_CITATION_ANCHOR_OPEN_RE.findall(str(text or "")))


def _strip_html_with_index_map(text: str) -> tuple[str, list[int]]:
    raw = str(text or "")
    plain_chars: list[str] = []
    index_map: list[int] = []
    in_tag = False
    for idx, char in enumerate(raw):
        if char == "<":
            in_tag = True
            continue
        if not in_tag:
            plain_chars.append(char)
            index_map.append(idx)
            continue
        if char == ">":
            in_tag = False
    return "".join(plain_chars), index_map


def _remove_inline_marker_tokens_with_index_map(
    plain_text: str,
    index_map: list[int],
) -> tuple[str, list[int]]:
    if not plain_text or not index_map or len(plain_text) != len(index_map):
        return plain_text, index_map
    stripped_chars: list[str] = []
    stripped_map: list[int] = []
    cursor = 0
    while cursor < len(plain_text):
        marker_match = re.match(
            r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})",
            plain_text[cursor:],
        )
        if marker_match:
            cursor += marker_match.end()
            continue
        stripped_chars.append(plain_text[cursor])
        stripped_map.append(index_map[cursor])
        cursor += 1
    return "".join(stripped_chars), stripped_map


def _dedupe_duplicate_answer_passes(answer: str) -> str:
    text = str(answer or "")
    if not text:
        return text
    if _count_citation_anchors(text) <= 0:
        return text

    plain, index_map = _strip_html_with_index_map(text)
    plain, index_map = _remove_inline_marker_tokens_with_index_map(plain, index_map)
    if not plain or not index_map:
        return text
    plain_start = next((idx for idx, char in enumerate(plain) if not char.isspace()), -1)
    if plain_start < 0:
        return text

    window = plain[plain_start : plain_start + 320]
    if len(window) < 120:
        return text
    sentence_match = re.search(r".{48,260}?[.!?]", window)
    if sentence_match:
        leading_signature = sentence_match.group(0).strip()
    else:
        leading_signature = window[:180].strip()
    leading_signature = re.sub(r"[\s\.,;:!?]+$", "", leading_signature).strip()
    if len(leading_signature) < 48:
        return text

    second_plain_idx = plain.find(leading_signature, plain_start + len(leading_signature))
    if second_plain_idx <= plain_start or second_plain_idx >= len(index_map):
        return text

    second_html_idx = index_map[second_plain_idx]
    if second_html_idx <= 0 or second_html_idx >= len(text):
        return text

    prefix_html = text[:second_html_idx]
    suffix_html = text[second_html_idx:]
    prefix_anchor_count = _count_citation_anchors(prefix_html)
    suffix_anchor_count = _count_citation_anchors(suffix_html)
    if prefix_anchor_count == suffix_anchor_count:
        prefix_plain = re.sub(
            r"\s+",
            " ",
            _clean_text(_HTML_TAG_RE.sub(" ", prefix_html)).strip().lower(),
        )
        suffix_plain = re.sub(
            r"\s+",
            " ",
            _clean_text(_HTML_TAG_RE.sub(" ", suffix_html)).strip().lower(),
        )
        if prefix_plain and prefix_plain == suffix_plain:
            trimmed = prefix_html.rstrip()
            return trimmed if trimmed else text
        return text
    if suffix_anchor_count > prefix_anchor_count:
        trimmed = suffix_html.lstrip()
        return trimmed if trimmed else text

    trimmed = prefix_html.rstrip()
    return trimmed if trimmed else text


def _looks_like_structured_response(body: str) -> bool:
    text = str(body or "")
    if not text.strip():
        return True
    if re.search(r"(^|\n)\s*#{1,6}\s+\S", text):
        return True
    if re.search(r"(^|\n)\s*(?:[-*]\s+\S|\d+\.\s+\S)", text):
        return True
    if re.search(r"<(?:h[1-6]|ul|ol|table|blockquote|p|pre)\b", text, flags=re.IGNORECASE):
        return True
    paragraph_blocks = [row for row in text.split("\n\n") if row.strip()]
    if len(paragraph_blocks) >= 2:
        return True
    return False


def _section_title_key(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def _diagnostics_requested_in_question(question: str) -> bool:
    prompt = " ".join(str(question or "").split()).strip().lower()
    if not prompt:
        return False
    return bool(
        re.search(
            r"\b(debug|diagnostic|logs?|trace|contract gate|delivery status|verification checks)\b",
            prompt,
        )
    )


def _strip_fast_qa_noise_sections(answer: str, *, question: str = "") -> str:
    text = str(answer or "")
    if not text.strip() or _diagnostics_requested_in_question(question):
        return text
    matches = list(_TOP_LEVEL_MD_HEADING_RE.finditer(text))
    if not matches:
        return text

    kept_chunks: list[str] = []
    cursor = 0
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        kept_chunks.append(text[cursor:section_start])
        title_key = _section_title_key(match.group(1))
        noisy = (
            title_key in _FAST_QA_NOISE_SECTION_TITLES
            or any(token in title_key for token in _FAST_QA_NOISE_SECTION_SUBSTRINGS)
        )
        if not noisy:
            kept_chunks.append(text[section_start:section_end])
        cursor = section_end
    kept_chunks.append(text[cursor:])
    normalized = "".join(kept_chunks)
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
    return normalized.strip()


def _format_notebook_style_layout(answer: str) -> str:
    text = str(answer or "")
    if not text.strip():
        return text

    body, tail = _split_answer_for_inline_injection(text)
    if _looks_like_structured_response(body):
        return text

    cleaned_body = _clean_text(body)
    if not cleaned_body:
        return text

    sentence_segments = [segment.strip() for segment in _SENTENCE_SEGMENT_RE.findall(body) if segment.strip()]
    if len(sentence_segments) < 3:
        return text

    # Keep short answers intact so the model can choose its own layout.
    if len(cleaned_body) < 260:
        return text

    # Paragraphize dense one-block output without imposing fixed headings.
    paragraphs: list[str] = []
    chunk: list[str] = []
    chunk_chars = 0
    for sentence in sentence_segments:
        sentence_chars = len(_clean_text(sentence))
        if chunk and (len(chunk) >= 3 or (chunk_chars + sentence_chars) > 420):
            paragraphs.append(" ".join(chunk).strip())
            chunk = [sentence]
            chunk_chars = sentence_chars
            continue
        chunk.append(sentence)
        chunk_chars += sentence_chars
    if chunk:
        paragraphs.append(" ".join(chunk).strip())

    if len(paragraphs) < 2:
        return text

    rebuilt_body = "\n\n".join(paragraphs)
    if tail:
        return f"{rebuilt_body.rstrip()}\n\n{tail.lstrip()}"
    return rebuilt_body


def assign_fast_source_refs(
    snippets: list[dict[str, Any]],
    *,
    strength_ordering: bool | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ref_by_key: dict[tuple[str, str, str], int] = {}
    ref_index_by_id: dict[int, int] = {}
    refs: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    ordering_enabled = (
        MAIA_CITATION_STRENGTH_ORDERING_ENABLED
        if strength_ordering is None
        else bool(strength_ordering)
    )

    for snippet in snippets:
        source_id = str(snippet.get("source_id", "") or "").strip()
        source_name = str(snippet.get("source_name", "Indexed file"))
        is_primary_source = bool(snippet.get("is_primary_source"))
        source_name_url = source_name if source_name.strip().lower().startswith(("http://", "https://")) else ""
        source_url = _normalize_source_url(
            snippet.get("source_url")
            or snippet.get("page_url")
            or snippet.get("url")
            or source_name_url
        )
        page_label = str(snippet.get("page_label", "") or "").strip()
        unit_id = str(snippet.get("unit_id", "") or "").strip()
        snippet_selector = str(snippet.get("selector", "") or "").strip()
        match_quality = str(snippet.get("match_quality", "") or "").strip() or "estimated"
        try:
            char_start = int(snippet.get("char_start", 0) or 0) if str(snippet.get("char_start", "")).strip() else 0
        except Exception:
            char_start = 0
        try:
            char_end = int(snippet.get("char_end", 0) or 0) if str(snippet.get("char_end", "")).strip() else 0
        except Exception:
            char_end = 0
        snippet_boxes = _normalize_highlight_boxes(snippet.get("highlight_boxes"))
        phrase = _snippet_signature_text(snippet.get("text", ""))
        snippet_strength = _snippet_strength_score(snippet)
        dedup_span = (
            unit_id
            if (MAIA_CITATION_UNIFIED_REFS_ENABLED and unit_id)
            else snippet_selector or phrase
        )
        key = (source_id or source_name, page_label, dedup_span)
        ref_id = ref_by_key.get(key)
        if ref_id is None:
            ref_id = len(refs) + 1
            ref_by_key[key] = ref_id
            ref_index_by_id[ref_id] = len(refs)
            label = source_name
            if page_label:
                label += f" (page {page_label})"
            refs.append(
                {
                    "id": ref_id,
                    "source_id": source_id,
                    "source_name": source_name,
                    "page_label": page_label,
                    "label": label,
                    "phrase": phrase,
                    "source_url": source_url,
                    "unit_id": unit_id,
                    "selector": snippet_selector,
                    "char_start": char_start,
                    "char_end": char_end,
                    "match_quality": match_quality,
                    "highlight_boxes": snippet_boxes,
                    "strength_score": snippet_strength,
                    "is_primary_source": is_primary_source,
                    "source_type": _source_type_from_name(source_name),
                }
            )
        else:
            existing_idx = ref_index_by_id.get(ref_id)
            if existing_idx is not None:
                existing_ref = refs[existing_idx]
                if snippet_boxes:
                    existing_ref["highlight_boxes"] = _merge_highlight_boxes(
                        _normalize_highlight_boxes(existing_ref.get("highlight_boxes")),
                        snippet_boxes,
                    )
                if source_url and not _normalize_source_url(existing_ref.get("source_url")):
                    existing_ref["source_url"] = source_url
                if is_primary_source:
                    existing_ref["is_primary_source"] = True
                existing_ref["strength_score"] = max(
                    _score_value(existing_ref.get("strength_score")),
                    snippet_strength,
                )
                if unit_id and not str(existing_ref.get("unit_id", "")).strip():
                    existing_ref["unit_id"] = unit_id
                if snippet_selector and not str(existing_ref.get("selector", "")).strip():
                    existing_ref["selector"] = snippet_selector
                if match_quality and str(existing_ref.get("match_quality", "")).strip() in {"", "estimated"}:
                    existing_ref["match_quality"] = match_quality
                if char_start > 0 and int(existing_ref.get("char_start", 0) or 0) <= 0:
                    existing_ref["char_start"] = char_start
                if char_end > char_start and int(existing_ref.get("char_end", 0) or 0) <= 0:
                    existing_ref["char_end"] = char_end

        enriched_item = dict(snippet)
        enriched_item["ref_id"] = ref_id
        enriched_item["strength_score"] = snippet_strength
        enriched_item["unit_id"] = unit_id
        if snippet_selector:
            enriched_item["selector"] = snippet_selector
        if char_start > 0:
            enriched_item["char_start"] = char_start
        if char_end > char_start:
            enriched_item["char_end"] = char_end
        enriched_item["match_quality"] = match_quality
        enriched_item["is_primary_source"] = is_primary_source
        if snippet_boxes:
            enriched_item["highlight_boxes"] = snippet_boxes
        if source_url:
            enriched_item["source_url"] = source_url
        enriched.append(enriched_item)

    if ordering_enabled and refs:
        ranked_refs = sorted(
            refs,
            key=lambda ref: (
                0 if bool(ref.get("is_primary_source")) else 1,
                -_score_value(ref.get("strength_score")),
                -_score_value(ref.get("llm_trulens_score")),
                str(ref.get("source_id", "") or ""),
                str(ref.get("page_label", "") or ""),
                str(ref.get("unit_id", "") or ""),
                str(ref.get("phrase", "") or ""),
            ),
        )
        old_to_new: dict[int, int] = {}
        normalized_refs: list[dict[str, Any]] = []
        for index, ref in enumerate(ranked_refs, start=1):
            previous_id = int(ref.get("id", 0) or 0)
            if previous_id > 0:
                old_to_new[previous_id] = index
            next_ref = dict(ref)
            next_ref["id"] = index
            normalized_refs.append(next_ref)
        refs = normalized_refs
        normalized_enriched: list[dict[str, Any]] = []
        for row in enriched:
            previous_id = int(row.get("ref_id", 0) or 0)
            next_row = dict(row)
            if previous_id > 0:
                next_row["ref_id"] = old_to_new.get(previous_id, previous_id)
            normalized_enriched.append(next_row)
        enriched = sorted(
            normalized_enriched,
            key=lambda row: (
                int(row.get("ref_id", 0) or 0),
                -_score_value(row.get("strength_score")),
            ),
        )

    return enriched, refs


def collect_cited_ref_ids(answer: str) -> list[int]:
    text = str(answer or "")
    if not text:
        return []
    seen: set[int] = set()
    ordered: list[int] = []
    for match in re.finditer(r"#evidence-(\d{1,4})", text, flags=re.IGNORECASE):
        ref_id = int(match.group(1))
        if ref_id <= 0 or ref_id in seen:
            continue
        seen.add(ref_id)
        ordered.append(ref_id)
    if ordered:
        return ordered
    for match in _INLINE_REF_TOKEN_RE.finditer(text):
        ref_id = int(match.group(1))
        if ref_id <= 0 or ref_id in seen:
            continue
        seen.add(ref_id)
        ordered.append(ref_id)
    return ordered


def build_source_usage(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    answer_text: str,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    if enabled is None:
        enabled = MAIA_SOURCE_USAGE_HEATMAP_ENABLED
    if not enabled:
        return []
    if not snippets_with_refs and not refs:
        return []

    ref_by_id = {int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0}
    cited_ref_ids = set(collect_cited_ref_ids(answer_text))

    bucket_by_source: dict[str, dict[str, Any]] = {}
    for snippet in snippets_with_refs:
        source_id = str(snippet.get("source_id", "") or "").strip()
        source_name = str(snippet.get("source_name", "Indexed file") or "Indexed file")
        source_key = source_id or f"name:{source_name}"
        bucket = bucket_by_source.get(source_key)
        if bucket is None:
            bucket = {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": _source_type_from_name(source_name),
                "retrieved_count": 0,
                "cited_count": 0,
                "max_strength_score": 0.0,
                "avg_strength_score": 0.0,
                "_strength_total": 0.0,
                "_strength_count": 0,
            }
            bucket_by_source[source_key] = bucket

        bucket["retrieved_count"] = int(bucket.get("retrieved_count", 0)) + 1
        strength = _score_value(snippet.get("strength_score"))
        bucket["max_strength_score"] = max(_score_value(bucket.get("max_strength_score")), strength)
        bucket["_strength_total"] = _score_value(bucket.get("_strength_total")) + strength
        bucket["_strength_count"] = int(bucket.get("_strength_count", 0)) + 1

        ref_id = int(snippet.get("ref_id", 0) or 0)
        if ref_id > 0 and ref_id in cited_ref_ids:
            bucket["cited_count"] = int(bucket.get("cited_count", 0)) + 1

    # If citations were injected but not present in snippets list, backfill from refs.
    for ref_id in cited_ref_ids:
        ref = ref_by_id.get(ref_id)
        if not ref:
            continue
        source_id = str(ref.get("source_id", "") or "").strip()
        source_name = str(ref.get("source_name", "Indexed file") or "Indexed file")
        source_key = source_id or f"name:{source_name}"
        bucket = bucket_by_source.get(source_key)
        if bucket is None:
            strength = _score_value(ref.get("strength_score"))
            bucket = {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": _source_type_from_name(source_name),
                "retrieved_count": 0,
                "cited_count": 1,
                "max_strength_score": strength,
                "avg_strength_score": strength,
                "_strength_total": strength,
                "_strength_count": 1,
            }
            bucket_by_source[source_key] = bucket
            continue
        bucket["cited_count"] = max(int(bucket.get("cited_count", 0)), 1)

    total_cited = sum(max(0, int(bucket.get("cited_count", 0))) for bucket in bucket_by_source.values())
    usage_rows: list[dict[str, Any]] = []
    for bucket in bucket_by_source.values():
        strength_count = max(1, int(bucket.get("_strength_count", 0)))
        avg_strength = _score_value(bucket.get("_strength_total")) / float(strength_count)
        cited_count = max(0, int(bucket.get("cited_count", 0)))
        usage_rows.append(
            {
                "source_id": str(bucket.get("source_id", "") or ""),
                "source_name": str(bucket.get("source_name", "Indexed file") or "Indexed file"),
                "source_type": str(bucket.get("source_type", "file") or "file"),
                "retrieved_count": max(0, int(bucket.get("retrieved_count", 0))),
                "cited_count": cited_count,
                "max_strength_score": round(_score_value(bucket.get("max_strength_score")), 6),
                "avg_strength_score": round(avg_strength, 6),
                "citation_share": round(
                    (float(cited_count) / float(total_cited)) if total_cited > 0 else 0.0,
                    6,
                ),
            }
        )

    usage_rows.sort(
        key=lambda item: (
            -int(item.get("cited_count", 0)),
            -int(item.get("retrieved_count", 0)),
            -_score_value(item.get("max_strength_score")),
            str(item.get("source_name", "") or ""),
        )
    )
    return usage_rows


def build_claim_signal_summary(
    *,
    answer_text: str,
    refs: list[dict[str, Any]],
    enabled: bool | None = None,
) -> dict[str, Any]:
    if enabled is None:
        enabled = MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED
    if not enabled:
        return {}

    text = str(answer_text or "")
    if not text.strip() or not refs:
        return {}

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    if not ref_by_id:
        return {}

    rows: list[dict[str, Any]] = []
    supported = 0
    contradicted = 0
    mixed = 0

    for segment_match in _SENTENCE_SEGMENT_RE.finditer(text):
        segment = segment_match.group(0)
        if not segment.strip():
            continue
        ref_ids = {
            int(match)
            for match in re.findall(r"#evidence-(\d{1,4})", segment, flags=re.IGNORECASE)
            if int(match) in ref_by_id
        }
        if not ref_ids:
            ref_ids = {
                int(match)
                for match in re.findall(r"(?:\[|【|ã€|\{)\s*(\d{1,4})\s*(?:\]|】|ã€‘|\})", segment)
                if int(match) in ref_by_id
            }
        if not ref_ids:
            continue

        cleaned_claim = _clean_text(
            re.sub(
                r"(?:\[|【|ã€|\{)\s*(\d{1,4})\s*(?:\]|】|ã€‘|\})",
                "",
                _CITATION_ANCHOR_RE.sub("", segment),
            )
        )
        if len(cleaned_claim) < 16:
            continue

        support_votes = 0
        contradiction_votes = 0
        if len(ref_ids) >= 2:
            for left_id, right_id in combinations(sorted(ref_ids), 2):
                left = ref_by_id.get(left_id, {})
                right = ref_by_id.get(right_id, {})
                left_tokens = _tokens(
                    " ".join(
                        [
                            str(left.get("phrase", "") or ""),
                            str(left.get("label", "") or ""),
                            str(left.get("source_name", "") or ""),
                        ]
                    )
                )
                right_tokens = _tokens(
                    " ".join(
                        [
                            str(right.get("phrase", "") or ""),
                            str(right.get("label", "") or ""),
                            str(right.get("source_name", "") or ""),
                        ]
                    )
                )
                if not left_tokens or not right_tokens:
                    continue
                inter = len(left_tokens & right_tokens)
                union = len(left_tokens | right_tokens)
                jaccard = (inter / float(union)) if union > 0 else 0.0
                if jaccard >= 0.22:
                    support_votes += 1
                elif jaccard <= 0.08:
                    contradiction_votes += 1

        if support_votes > 0 and contradiction_votes > 0:
            status = "mixed"
            mixed += 1
        elif support_votes > 0:
            status = "supported"
            supported += 1
        elif contradiction_votes > 0:
            status = "contradicted"
            contradicted += 1
        else:
            status = "insufficient"

        rows.append(
            {
                "claim": cleaned_claim,
                "ref_ids": sorted(ref_ids),
                "status": status,
                "support_votes": support_votes,
                "contradiction_votes": contradiction_votes,
            }
        )
        if len(rows) >= 16:
            break

    if not rows:
        return {}
    return {
        "claims_evaluated": len(rows),
        "supported_claims": supported,
        "contradicted_claims": contradicted,
        "mixed_claims": mixed,
        "rows": rows,
    }


def build_citation_quality_metrics(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    answer_text: str,
) -> dict[str, Any]:
    cited_ref_ids = set(collect_cited_ref_ids(answer_text))
    refs_with_boxes = sum(1 for ref in refs if _normalize_highlight_boxes(ref.get("highlight_boxes")))
    refs_with_unit_id = sum(1 for ref in refs if str(ref.get("unit_id", "") or "").strip())
    refs_with_offsets = sum(
        1
        for ref in refs
        if (_to_int(ref.get("char_start", 0)) or 0) > 0
        and (_to_int(ref.get("char_end", 0)) or 0) > (_to_int(ref.get("char_start", 0)) or 0)
    )
    match_quality_counter: dict[str, int] = {}
    for ref in refs:
        quality = str(ref.get("match_quality", "") or "").strip().lower() or "estimated"
        match_quality_counter[quality] = int(match_quality_counter.get(quality, 0)) + 1
    return {
        "retrieved_snippets": len(snippets_with_refs),
        "total_refs": len(refs),
        "cited_refs": len(cited_ref_ids),
        "refs_with_boxes": refs_with_boxes,
        "refs_with_unit_id": refs_with_unit_id,
        "refs_with_offsets": refs_with_offsets,
        "anchor_attribute_completeness": (
            round(
                (
                    (refs_with_boxes + refs_with_unit_id + refs_with_offsets)
                    / float(max(1, len(refs) * 3))
                ),
                6,
            )
            if refs
            else 0.0
        ),
        "match_quality_counts": match_quality_counter,
    }


def resolve_required_citation_mode(citation_mode: str | None) -> str:
    mode = (citation_mode or "").strip().lower()
    if mode == CITATION_MODE_INLINE:
        return CITATION_MODE_INLINE
    return CITATION_MODE_INLINE


def render_fast_citation_links(
    answer: str,
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str:
    if not answer.strip():
        return answer

    answer = _realign_bracket_ref_numbers(answer, refs)
    answer = _inject_claim_level_bracket_citations(answer, refs)

    if "class='citation'" in answer or 'class="citation"' in answer:
        # Reposition legacy/model-linked anchors at claim level by converting them
        # back to bracket refs, then running the same claim-level citation flow.
        marker_text = _anchors_to_bracket_markers(_augment_existing_citation_anchors(answer, refs))
        marker_text = _realign_bracket_ref_numbers(marker_text, refs)
        marker_text = _inject_claim_level_bracket_citations(marker_text, refs)
        ref_by_id: dict[int, dict[str, Any]] = {
            int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
        }
        sorted_ref_ids = sorted(ref_by_id.keys())

        def resolve_ref(ref_num: int) -> dict[str, Any] | None:
            if not sorted_ref_ids:
                return None
            if ref_num >= 1 and ref_num in ref_by_id:
                return ref_by_id[ref_num]
            if ref_num >= 1:
                nearest_ref_id = min(sorted_ref_ids, key=lambda item: (abs(item - ref_num), item))
                return ref_by_id.get(nearest_ref_id)
            return ref_by_id.get(sorted_ref_ids[0])

        def replace_ref(match: re.Match[str]) -> str:
            ref_num = int(match.group(1))
            ref = resolve_ref(ref_num)
            if not ref:
                return match.group(0)
            return _citation_anchor(ref) or match.group(0)

        enriched = _INLINE_REF_TOKEN_RE.sub(replace_ref, marker_text)
        enriched = _inject_inline_citations(enriched, refs)
        return _normalize_visible_inline_citations(enriched)

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    sorted_ref_ids = sorted(ref_by_id.keys())

    def resolve_ref(ref_num: int) -> dict[str, Any] | None:
        if not sorted_ref_ids:
            return None
        if ref_num >= 1 and ref_num in ref_by_id:
            return ref_by_id[ref_num]
        if ref_num >= 1:
            nearest_ref_id = min(sorted_ref_ids, key=lambda item: (abs(item - ref_num), item))
            return ref_by_id.get(nearest_ref_id)
        return ref_by_id.get(sorted_ref_ids[0])

    def replace_ref(match: re.Match[str]) -> str:
        ref_num = int(match.group(1))
        ref = resolve_ref(ref_num)
        if not ref:
            return match.group(0)
        return _citation_anchor(ref) or match.group(0)

    enriched = _INLINE_REF_TOKEN_RE.sub(replace_ref, answer)
    enriched = _inject_inline_citations(enriched, refs)
    enriched = _normalize_visible_inline_citations(enriched)

    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched

    if not refs:
        return enriched

    fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
    return _normalize_visible_inline_citations(f"{enriched}\n\nEvidence: {fallback_refs}")


def _extract_info_refs(info_html: str) -> list[dict[str, Any]]:
    text = _normalize_info_evidence_html(str(info_html or ""))
    if not text:
        return []

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
            if summary_match:
                page_label = summary_match.group(1).strip()
            else:
                page_label = ""
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
                    match_quality_match.group(1).strip().lower()
                    if match_quality_match
                    else "estimated"
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


def enforce_required_citations(
    *,
    answer: str,
    info_html: str,
    citation_mode: str | None,
) -> str:
    text = (answer or "").strip()
    if not text:
        return text

    mode = resolve_required_citation_mode(citation_mode)
    refs = _resolve_citation_refs(info_html=info_html, answer=text)
    layout_seed = text
    if "class='citation'" in layout_seed or 'class="citation"' in layout_seed:
        layout_seed = _anchors_to_bracket_markers(layout_seed)
    layout_seed = _format_notebook_style_layout(layout_seed)
    enriched = render_fast_citation_links(answer=layout_seed, refs=refs, citation_mode=mode)
    enriched = _inject_inline_citations(enriched, refs)
    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return _dedupe_duplicate_answer_passes(enriched)
    if refs:
        return _dedupe_duplicate_answer_passes(enriched)
    return (
        f"{enriched}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def append_required_citation_suffix(*, answer: str, info_html: str) -> str:
    raw_text = str(answer or "")
    if not raw_text.strip():
        return ""

    refs = _resolve_citation_refs(info_html=info_html, answer=raw_text)
    if refs:
        layout_seed = raw_text
        if "class='citation'" in layout_seed or 'class="citation"' in layout_seed:
            layout_seed = _anchors_to_bracket_markers(layout_seed)
        layout_seed = _format_notebook_style_layout(layout_seed)
        enriched = render_fast_citation_links(
            answer=layout_seed,
            refs=refs,
            citation_mode=CITATION_MODE_INLINE,
        )
        enriched = _inject_inline_citations(enriched, refs)
        enriched = _normalize_visible_inline_citations(enriched)
        enriched = _dedupe_duplicate_answer_passes(enriched)
        if "class='citation'" in enriched or 'class="citation"' in enriched:
            return enriched
        fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
        return f"{enriched}\n\nEvidence: {fallback_refs}"
    if "class='citation'" in raw_text or 'class="citation"' in raw_text:
        return _dedupe_duplicate_answer_passes(_normalize_visible_inline_citations(raw_text))
    return (
        f"{raw_text}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def normalize_fast_answer(answer: str, *, question: str = "") -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    # Keep headings readable when models place them mid-line.
    text = re.sub(r"(?<!\n)(#{2,6}\s+)", r"\n\n\1", text)
    # Collapse duplicated heading markers like "### ## Title" into a single heading.
    text = re.sub(r"(^|\n)\s*#{1,6}\s*#{1,6}\s*", r"\1## ", text)
    text = _strip_fast_qa_noise_sections(text, question=question)

    # Remove malformed bold markers that often break markdown rendering.
    malformed_bold = bool(re.search(r"#{2,6}\s*\*\*|\*\*[^*]+-\s*\*\*", text))
    if malformed_bold or text.count("**") % 2 == 1:
        text = text.replace("**", "")

    # Drop duplicated long paragraphs that models sometimes emit twice.
    blocks = [row.strip() for row in text.split("\n\n")]
    deduped_blocks: list[str] = []
    seen_signatures: set[str] = set()
    for block in blocks:
        if not block:
            continue
        signature = re.sub(r"(?:\[|【|ã€|\{)\s*\d{1,4}\s*(?:\]|】|ã€‘|\})", "", block)
        signature = re.sub(r"\s+", " ", signature).strip().lower()
        if len(signature) >= 120 and signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduped_blocks.append(block)
    text = "\n\n".join(deduped_blocks)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
        excerpt = html.escape(
            _compact_evidence_extract(str(snippet.get("text", "") or ""))
        )
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
        details_file_attr = (
            f" data-file-id='{html.escape(source_id, quote=True)}'" if source_id else ""
        )
        details_source_url_attr = (
            f" data-source-url='{html.escape(source_url, quote=True)}'" if source_url else ""
        )
        details_unit_attr = (
            f" data-unit-id='{html.escape(unit_id[:160], quote=True)}'" if unit_id else ""
        )
        details_match_quality_attr = (
            f" data-match-quality='{html.escape(match_quality[:32], quote=True)}'"
            if match_quality
            else ""
        )
        details_char_start_attr = f" data-char-start='{char_start}'" if char_start > 0 else ""
        details_char_end_attr = f" data-char-end='{char_end}'" if char_end > char_start else ""
        strength_score = _score_value(snippet.get("strength_score"))
        strength_tier = _strength_tier(strength_score)
        details_strength_attr = (
            f" data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'"
            if strength_score > 0
            else ""
        )
        details_strength_tier_attr = (
            f" data-strength-tier='{strength_tier}'"
            if MAIA_CITATION_STRENGTH_BADGES_ENABLED and strength_score > 0
            else ""
        )
        boxes_payload = _serialize_highlight_boxes(snippet.get("highlight_boxes"))
        details_boxes_attr = (
            f" data-boxes='{html.escape(boxes_payload, quote=True)}'" if boxes_payload else ""
        )
        source_label = source_name
        if ref_id > 0:
            source_label = f"[{ref_id}] {source_name}"
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
