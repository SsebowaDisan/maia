from __future__ import annotations

import re
from typing import Any

from .anchors import (
    _anchors_to_bracket_markers,
    _augment_existing_citation_anchors,
    _citation_anchor,
)
from .context import _best_ref_for_context, _context_window, _is_claim_like_fragment
from .shared import (
    _INLINE_REF_TOKEN_RE,
    _MARKDOWN_LINK_RE,
    _SENTENCE_SEGMENT_RE,
    _URL_TOKEN_RE,
    _clean_text,
    _split_answer_for_inline_injection,
)
from .visible import _normalize_visible_inline_citations


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
        if best_ref_id is None or score < 0.16:
            return match.group(0)
        return f"[{best_ref_id}]"

    realigned_body = _INLINE_REF_TOKEN_RE.sub(replace_ref, body)
    if tail:
        return f"{realigned_body.rstrip()}\n\n{tail.lstrip()}"
    return realigned_body


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
