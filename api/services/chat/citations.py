from __future__ import annotations

import html
import json
import re
from typing import Any

from .constants import (
    MAIA_CITATION_STRENGTH_ORDERING_ENABLED,
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
_DETAILS_BOXES_RE = re.compile(r"data-boxes=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_DETAILS_STRENGTH_RE = re.compile(r"data-strength=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]{3,}")
_SENTENCE_SEGMENT_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:  # NaN
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


def _snippet_strength_score(snippet: dict[str, Any]) -> float:
    base = (
        _score_value(snippet.get("llm_trulens_score"))
        + _score_value(snippet.get("rerank_score"))
        + _score_value(snippet.get("vector_score"))
    )
    exact_match_bonus = 0.05 if bool(snippet.get("is_exact_match", False)) else 0.0
    span_text = str(snippet.get("text", "") or "")
    span_length_bonus = min(0.10, len(span_text) / 4000.0)
    # Keep retrieval score as a weak fallback signal when explicit model scores are absent.
    retrieval_bonus = min(0.05, max(0.0, _score_value(snippet.get("score"))) / 1000.0)
    return base + exact_match_bonus + span_length_bonus + retrieval_bonus


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
    return {token for token in _TOKEN_RE.findall(normalized) if len(token) >= 3}


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
        overlap = len(context_tokens & ref_tokens)
        if overlap <= 0:
            continue
        precision = overlap / max(1, len(context_tokens))
        recall = overlap / max(1, len(ref_tokens))
        # Favor excerpts that cover the local claim with minimal noise.
        score = (precision * 0.65) + (recall * 0.35)
        if score > best_score:
            best_score = score
            best_ref_id = ref_id
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
    trimmed = re.sub(r"^[-*•\d\.\)\(\s]+", "", normalized)
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
    fallback_ref_id = min(ref_by_id.keys())

    rebuilt: list[str] = []
    cursor = 0
    for match in _SENTENCE_SEGMENT_RE.finditer(line):
        start, end = match.span()
        rebuilt.append(line[cursor:start])
        segment = line[start:end]
        cleaned = _clean_text(segment)
        should_cite = _is_claim_like_fragment(segment)
        already_cited = bool(
            re.search(r"\[\d{1,3}\]", segment)
            or "class='citation'" in segment
            or 'class="citation"' in segment
        )
        if should_cite and not already_cited and cleaned:
            best_ref_id, _score = _best_ref_for_context(cleaned, refs)
            ref_id = best_ref_id if best_ref_id in ref_by_id else fallback_ref_id
            marker = f"[{ref_id}]"
            segment_stripped = segment.rstrip()
            segment = f"{segment_stripped} {marker}{segment[len(segment_stripped):]}"
        rebuilt.append(segment)
        cursor = end
    rebuilt.append(line[cursor:])
    return "".join(rebuilt)


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
    if not re.search(r"\[\d{1,3}\]", body):
        return text

    max_ref = max(int(ref.get("id", 0) or 0) for ref in refs) if refs else 0
    if max_ref <= 0:
        return text

    def replace_ref(match: re.Match[str]) -> str:
        original_ref = int(match.group(1))
        # Keep unknown markers untouched.
        if original_ref < 1 or original_ref > max_ref:
            return match.group(0)
        context = _context_window(body, match.start())
        best_ref_id, score = _best_ref_for_context(context, refs)
        # Require a minimum confidence before overriding the model's numeric ref.
        if best_ref_id is None or score < 0.16:
            return match.group(0)
        return f"[{best_ref_id}]"

    realigned_body = re.sub(r"\[(\d{1,3})\]", replace_ref, body)
    if tail:
        return f"{realigned_body.rstrip()}\n\n{tail.lstrip()}"
    return realigned_body


def _citation_anchor(ref: dict[str, Any]) -> str:
    ref_id = int(ref.get("id", 0) or 0)
    if ref_id <= 0:
        return ""
    file_id = str(ref.get("source_id", "") or "").strip()
    page_label = str(ref.get("page_label", "") or "").strip()
    phrase = str(ref.get("phrase", "") or "").strip()
    strength_score = _score_value(ref.get("strength_score"))
    boxes_payload = _serialize_highlight_boxes(ref.get("highlight_boxes"))
    attrs = [f"href='#evidence-{ref_id}'", f"id='citation-{ref_id}'", "class='citation'"]
    if file_id:
        attrs.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
    if page_label:
        attrs.append(f"data-page='{html.escape(page_label, quote=True)}'")
    if phrase:
        attrs.append(f"data-phrase='{html.escape(phrase[:CITATION_PHRASE_MAX_CHARS], quote=True)}'")
    if strength_score > 0:
        attrs.append(f"data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'")
    if boxes_payload:
        attrs.append(f"data-boxes='{html.escape(boxes_payload, quote=True)}'")
    return f"<a {' '.join(attrs)}>[{ref_id}]</a>"


def _clean_text(fragment: str) -> str:
    if not fragment:
        return ""
    without_tags = _HTML_TAG_RE.sub(" ", fragment)
    plain = html.unescape(without_tags)
    return _SPACE_RE.sub(" ", plain).strip()


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
        or re.search(r"\[\d{1,3}\]", text)
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
        anchor = _citation_anchor(refs[injected % len(refs)])
        if not anchor:
            continue
        lines[index] = f"{row.rstrip()} {anchor}"
        injected += 1
        if injected >= ref_limit:
            break

    if injected == 0 and body.strip():
        first_anchor = _citation_anchor(refs[0])
        if first_anchor:
            body = f"{body.rstrip()} {first_anchor}"
    else:
        body = "\n".join(lines)

    if tail:
        return f"{body.rstrip()}\n\n{tail.lstrip()}"
    return body


def _ref_id_from_anchor_open(anchor_open: str) -> int:
    href_match = re.search(
        r"href=['\"]#evidence-(\d{1,4})['\"]",
        anchor_open,
        flags=re.IGNORECASE,
    )
    if href_match:
        return int(href_match.group(1))
    id_match = re.search(
        r"id=['\"]citation-(\d{1,4})['\"]",
        anchor_open,
        flags=re.IGNORECASE,
    )
    if id_match:
        return int(id_match.group(1))
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

        additions: list[str] = []
        file_id = str(ref.get("source_id", "") or "").strip()
        page_label = str(ref.get("page_label", "") or "").strip()
        phrase = str(ref.get("phrase", "") or "").strip()
        strength_score = _score_value(ref.get("strength_score"))
        boxes_payload = _serialize_highlight_boxes(ref.get("highlight_boxes"))

        if file_id and not re.search(r"\bdata-file-id=['\"]", anchor_open, flags=re.IGNORECASE):
            additions.append(f"data-file-id='{html.escape(file_id, quote=True)}'")
        if page_label and not re.search(r"\bdata-page=['\"]", anchor_open, flags=re.IGNORECASE):
            additions.append(f"data-page='{html.escape(page_label, quote=True)}'")
        if phrase and not re.search(r"\bdata-phrase=['\"]", anchor_open, flags=re.IGNORECASE):
            additions.append(
                f"data-phrase='{html.escape(phrase[:CITATION_PHRASE_MAX_CHARS], quote=True)}'"
            )
        if strength_score > 0 and not re.search(r"\bdata-strength=['\"]", anchor_open, flags=re.IGNORECASE):
            additions.append(f"data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'")
        if boxes_payload and not re.search(r"\bdata-boxes=['\"]", anchor_open, flags=re.IGNORECASE):
            additions.append(f"data-boxes='{html.escape(boxes_payload, quote=True)}'")

        if not additions:
            return anchor_open
        return f"{anchor_open[:-1]} {' '.join(additions)}>"

    return _CITATION_ANCHOR_OPEN_RE.sub(replace_open, text)


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
        page_label = str(snippet.get("page_label", "") or "").strip()
        snippet_boxes = _normalize_highlight_boxes(snippet.get("highlight_boxes"))
        phrase = _snippet_signature_text(snippet.get("text", ""))
        snippet_strength = _snippet_strength_score(snippet)
        key = (source_id or source_name, page_label, phrase)
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
                    "highlight_boxes": snippet_boxes,
                    "strength_score": snippet_strength,
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
                existing_ref["strength_score"] = max(
                    _score_value(existing_ref.get("strength_score")),
                    snippet_strength,
                )

        enriched_item = dict(snippet)
        enriched_item["ref_id"] = ref_id
        enriched_item["strength_score"] = snippet_strength
        if snippet_boxes:
            enriched_item["highlight_boxes"] = snippet_boxes
        enriched.append(enriched_item)

    if ordering_enabled and refs:
        ranked_refs = sorted(
            refs,
            key=lambda ref: (
                -_score_value(ref.get("strength_score")),
                -_score_value(ref.get("llm_trulens_score")),
                str(ref.get("source_id", "") or ""),
                str(ref.get("page_label", "") or ""),
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
    for match in re.finditer(r"(?:#evidence-|\[)(\d{1,4})(?:\]|['\"])", text):
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
        # Already linked: avoid a second replacement pass that can nest anchors.
        enriched = _augment_existing_citation_anchors(answer, refs)
        return _inject_inline_citations(enriched, refs)

    ref_by_id: dict[int, dict[str, Any]] = {
        int(ref.get("id", 0) or 0): ref for ref in refs if int(ref.get("id", 0) or 0) > 0
    }
    max_ref = len(ref_by_id)

    def replace_ref(match: re.Match[str]) -> str:
        ref_num = int(match.group(1))
        if ref_num < 1 or ref_num > max_ref:
            return match.group(0)
        ref = ref_by_id.get(ref_num, {})
        return _citation_anchor(ref) or match.group(0)

    enriched = re.sub(r"\[(\d{1,3})\]", replace_ref, answer)
    enriched = _inject_inline_citations(enriched, refs)

    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched

    if not refs:
        return enriched

    fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
    return f"{enriched}\n\nEvidence: {fallback_refs}"


def _extract_info_refs(info_html: str) -> list[dict[str, Any]]:
    text = str(info_html or "")
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
        boxes_match = _DETAILS_BOXES_RE.search(tag)
        strength_match = _DETAILS_STRENGTH_RE.search(tag)
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
        highlight_boxes = _load_highlight_boxes_attr(boxes_match.group(1) if boxes_match else "")
        refs.append(
            {
                "id": ref_id,
                "source_id": source_id_match.group(1).strip() if source_id_match else "",
                "page_label": page_label,
                "label": f"Evidence {ref_id}",
                "phrase": phrase,
                "highlight_boxes": highlight_boxes,
                "strength_score": _score_value(strength_match.group(1) if strength_match else 0.0),
            }
        )
    refs.sort(key=lambda item: int(item.get("id", 0) or 0))
    return refs


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
    refs = _extract_info_refs(info_html)
    enriched = render_fast_citation_links(answer=text, refs=refs, citation_mode=mode)
    enriched = _inject_inline_citations(enriched, refs)
    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched
    if refs:
        return enriched
    return (
        f"{enriched}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def append_required_citation_suffix(*, answer: str, info_html: str) -> str:
    raw_text = str(answer or "")
    if not raw_text.strip():
        return ""
    if "class='citation'" in raw_text or 'class="citation"' in raw_text:
        return raw_text

    refs = _extract_info_refs(info_html)
    if refs:
        enriched = render_fast_citation_links(
            answer=raw_text,
            refs=refs,
            citation_mode=CITATION_MODE_INLINE,
        )
        enriched = _inject_inline_citations(enriched, refs)
        if "class='citation'" in enriched or 'class="citation"' in enriched:
            return enriched
        fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
        return f"{enriched}\n\nEvidence: {fallback_refs}"
    return (
        f"{raw_text}\n\n"
        "Evidence: internal execution trace (no external source references were returned by the retrieval pipeline)."
    )


def normalize_fast_answer(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return ""

    # Keep headings readable when models place them mid-line.
    text = re.sub(r"(?<!\n)(#{2,6}\s+)", r"\n\n\1", text)
    # Collapse duplicated heading markers like "### ## Title" into a single heading.
    text = re.sub(r"(^|\n)\s*#{1,6}\s*#{1,6}\s*", r"\1## ", text)

    # Remove malformed bold markers that often break markdown rendering.
    malformed_bold = bool(re.search(r"#{2,6}\s*\*\*|\*\*[^*]+-\s*\*\*", text))
    if malformed_bold or text.count("**") % 2 == 1:
        text = text.replace("**", "")

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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

        source_name = html.escape(str(snippet.get("source_name", "Indexed file")))
        page_label = html.escape(str(snippet.get("page_label", "") or ""))
        excerpt = html.escape(str(snippet.get("text", "") or "")[:1400])
        image_origin = snippet.get("image_origin")
        summary_label = f"Evidence [{ref_id}]" if ref_id > 0 else "Evidence"
        if page_label:
            summary_label += f" - page {page_label}"

        details_id = f" id='evidence-{ref_id}'" if ref_id > 0 else ""
        source_id = str(snippet.get("source_id", "") or "").strip()
        details_page_attr = f" data-page='{page_label}'" if page_label else ""
        details_file_attr = (
            f" data-file-id='{html.escape(source_id, quote=True)}'" if source_id else ""
        )
        strength_score = _score_value(snippet.get("strength_score"))
        details_strength_attr = (
            f" data-strength='{html.escape(f'{strength_score:.6f}', quote=True)}'"
            if strength_score > 0
            else ""
        )
        boxes_payload = _serialize_highlight_boxes(snippet.get("highlight_boxes"))
        details_boxes_attr = (
            f" data-boxes='{html.escape(boxes_payload, quote=True)}'" if boxes_payload else ""
        )
        source_label = source_name
        if ref_id > 0:
            source_label = f"[{ref_id}] {source_name}"
        block = (
            f"<details class='evidence'{details_id}{details_file_attr}{details_page_attr}{details_strength_attr}{details_boxes_attr} {'open' if not info_blocks else ''}>"
            f"<summary><i>{summary_label}</i></summary>"
            f"<div><b>Source:</b> {source_label}</div>"
            f"<div class='evidence-content'><b>Extract:</b> {excerpt}</div>"
        )
        if isinstance(image_origin, str) and image_origin.startswith("data:image/"):
            safe_src = html.escape(image_origin, quote=True)
            block += "<figure>" f"<img src=\"{safe_src}\" alt=\"evidence image\"/>" "</figure>"
        block += "</details>"
        info_blocks.append(block)
        if len(info_blocks) >= max_blocks:
            break
    return "".join(info_blocks)
