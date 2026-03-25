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


def _diversify_repeated_ref_numbers(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text or not refs:
        return text
    if "class='citation'" in text or 'class="citation"' in text:
        return text

    body, tail = _split_answer_for_inline_injection(text)
    matches = list(_INLINE_REF_TOKEN_RE.finditer(body))
    if len(matches) < 2:
        return text

    unique_markers = {int(match.group(1)) for match in matches}
    valid_ref_ids = {int(ref.get("id", 0) or 0) for ref in refs if int(ref.get("id", 0) or 0) > 0}
    if len(valid_ref_ids) < 2 or len(unique_markers) > 1:
        return text

    rebuilt: list[str] = []
    cursor = 0
    changed = False
    for segment_match in _SENTENCE_SEGMENT_RE.finditer(body):
        start, end = segment_match.span()
        rebuilt.append(body[cursor:start])
        segment = segment_match.group(0)
        segment_markers = list(_INLINE_REF_TOKEN_RE.finditer(segment))
        if not segment_markers or not _is_claim_like_fragment(segment):
            rebuilt.append(segment)
            cursor = end
            continue

        cleaned_segment = _clean_text(_INLINE_REF_TOKEN_RE.sub("", segment))
        best_ref_id, score = _best_ref_for_context(cleaned_segment, refs)
        if best_ref_id is None or best_ref_id not in valid_ref_ids or score < 0.08:
            rebuilt.append(segment)
            cursor = end
            continue

        first_marker = int(segment_markers[0].group(1))
        if first_marker != best_ref_id:
            changed = True

        replaced_segment = _INLINE_REF_TOKEN_RE.sub(f"[{best_ref_id}]", segment)
        rebuilt.append(replaced_segment)
        cursor = end

    rebuilt.append(body[cursor:])
    diversified_body = "".join(rebuilt)
    if not changed:
        return text
    if tail:
        return f"{diversified_body.rstrip()}\n\n{tail.lstrip()}"
    return diversified_body


def _inject_inline_citations(answer: str, refs: list[dict[str, Any]]) -> str:
    text = str(answer or "")
    if not text.strip() or not refs:
        return text
    if _has_inline_citation_markers(text):
        return text

    body, tail = _split_answer_for_inline_injection(text)
    lines = body.splitlines()
    ref_limit = max(1, len(refs))
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


def _enforce_paragraph_citation_coverage(answer: str, refs: list[dict[str, Any]]) -> str:
    """Ensure every substantive paragraph has at least one citation.

    Walks paragraphs (separated by blank lines). For each paragraph that:
    - is claim-like (>40 chars, not a heading/code/HTML)
    - has no bracket citation marker
    assigns the best-matching ref via context scoring.
    """
    text = str(answer or "")
    if not text.strip() or not refs:
        return text
    if "class='citation'" in text or 'class="citation"' in text:
        return text

    body, tail = _split_answer_for_inline_injection(text)
    paragraphs = re.split(r"\n\s*\n", body)
    if len(paragraphs) <= 1:
        return text

    out_paragraphs: list[str] = []
    changed = False
    for para in paragraphs:
        stripped = para.strip()
        # Skip non-claim paragraphs
        if not stripped or stripped.startswith("#") or stripped.startswith("```") or stripped.startswith("<"):
            out_paragraphs.append(para)
            continue
        if len(stripped) < 40:
            out_paragraphs.append(para)
            continue
        # Already has a citation marker — skip
        if _INLINE_REF_TOKEN_RE.search(stripped):
            out_paragraphs.append(para)
            continue
        # Find best ref for this paragraph
        cleaned = _clean_text(_INLINE_REF_TOKEN_RE.sub("", stripped))
        best_ref_id, score = _best_ref_for_context(cleaned, refs)
        if best_ref_id is not None and score >= 0.18:
            para = f"{para.rstrip()} [{best_ref_id}]"
            changed = True
        out_paragraphs.append(para)

    if not changed:
        return text
    rewritten_body = "\n\n".join(out_paragraphs)
    if tail:
        return f"{rewritten_body.rstrip()}\n\n{tail.lstrip()}"
    return rewritten_body


def _guard_citation_dominance(answer: str, refs: list[dict[str, Any]]) -> str:
    """Prevent one citation from dominating the entire answer.

    If a single ref accounts for >60% of all citation markers and there
    are 2+ other refs available, re-score over-represented paragraphs
    to redistribute citations.
    """
    text = str(answer or "")
    if not text.strip() or len(refs) < 2:
        return text

    body, tail = _split_answer_for_inline_injection(text)
    all_markers = list(_INLINE_REF_TOKEN_RE.finditer(body))
    if len(all_markers) < 3:
        return text

    # Count frequency of each ref ID
    freq: dict[int, int] = {}
    for m in all_markers:
        ref_id = int(m.group(1))
        freq[ref_id] = freq.get(ref_id, 0) + 1
    total = sum(freq.values())
    if total < 3:
        return text

    dominant_id = max(freq, key=lambda k: freq[k])
    dominance_ratio = freq[dominant_id] / total
    if dominance_ratio <= 0.60:
        return text

    # Re-score segments that use the dominant ref
    valid_ref_ids = {int(ref.get("id", 0) or 0) for ref in refs if int(ref.get("id", 0) or 0) > 0}
    rebuilt: list[str] = []
    cursor = 0
    changed = False

    for segment_match in _SENTENCE_SEGMENT_RE.finditer(body):
        start, end = segment_match.span()
        rebuilt.append(body[cursor:start])
        segment = segment_match.group(0)
        segment_markers = list(_INLINE_REF_TOKEN_RE.finditer(segment))

        if not segment_markers or int(segment_markers[0].group(1)) != dominant_id:
            rebuilt.append(segment)
            cursor = end
            continue

        # Re-score this segment excluding the dominant ref
        cleaned = _clean_text(_INLINE_REF_TOKEN_RE.sub("", segment))
        non_dominant_refs = [r for r in refs if int(r.get("id", 0) or 0) != dominant_id]
        best_alt_id, alt_score = _best_ref_for_context(cleaned, non_dominant_refs)

        if best_alt_id is not None and best_alt_id in valid_ref_ids and alt_score >= 0.22:
            replaced = _INLINE_REF_TOKEN_RE.sub(f"[{best_alt_id}]", segment)
            rebuilt.append(replaced)
            changed = True
        else:
            rebuilt.append(segment)
        cursor = end

    rebuilt.append(body[cursor:])
    if not changed:
        return text

    rewritten_body = "".join(rebuilt)
    if tail:
        return f"{rewritten_body.rstrip()}\n\n{tail.lstrip()}"
    return rewritten_body


def _collapse_single_ref_citation_noise(answer: str, refs: list[dict[str, Any]]) -> str:
    """Collapse repeated same-ref markers to one citation per paragraph.

    When only one ref is available, sentence-level repair can make the answer look
    amateur by appending the same citation to every sentence. Keep the answer
    grounded, but show a single citation at the end of each substantive paragraph.
    """
    text = str(answer or "")
    if not text.strip() or len(refs) != 1:
        return text

    ref_id = int(refs[0].get("id", 0) or 0)
    if ref_id <= 0:
        return text

    body, tail = _split_answer_for_inline_injection(text)
    paragraphs = re.split(r"\n\s*\n", body)
    changed = False
    rebuilt: list[str] = []
    marker_re = re.compile(rf"(?:\[\s*{ref_id}\s*\]\s*)+")

    for para in paragraphs:
        stripped = para.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("```")
            or stripped.startswith("<")
            or len(stripped) < 40
        ):
            rebuilt.append(para)
            continue

        marker_count = len(re.findall(rf"\[\s*{ref_id}\s*\]", para))
        if marker_count <= 1:
            rebuilt.append(para)
            continue

        normalized = marker_re.sub(" ", para)
        normalized = re.sub(r"\s+([,.;:])", r"\1", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized).strip()
        normalized = normalized.rstrip()
        if normalized.endswith((".", "!", "?")):
            normalized = f"{normalized} [{ref_id}]"
        else:
            normalized = f"{normalized}. [{ref_id}]"
        rebuilt.append(normalized)
        changed = True

    if not changed:
        return text

    rewritten_body = "\n\n".join(rebuilt)
    if tail:
        return f"{rewritten_body.rstrip()}\n\n{tail.lstrip()}"
    return rewritten_body


def render_fast_citation_links(
    answer: str,
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str:
    if not answer.strip():
        return answer

    answer = _realign_bracket_ref_numbers(answer, refs)
    answer = _diversify_repeated_ref_numbers(answer, refs)
    answer = _enforce_paragraph_citation_coverage(answer, refs)
    answer = _guard_citation_dominance(answer, refs)
    answer = _inject_claim_level_bracket_citations(answer, refs)
    answer = _collapse_single_ref_citation_noise(answer, refs)

    if "class='citation'" in answer or 'class="citation"' in answer:
        marker_text = _anchors_to_bracket_markers(_augment_existing_citation_anchors(answer, refs))
        marker_text = _realign_bracket_ref_numbers(marker_text, refs)
        marker_text = _diversify_repeated_ref_numbers(marker_text, refs)
        marker_text = _enforce_paragraph_citation_coverage(marker_text, refs)
        marker_text = _guard_citation_dominance(marker_text, refs)
        marker_text = _inject_claim_level_bracket_citations(marker_text, refs)
        marker_text = _collapse_single_ref_citation_noise(marker_text, refs)
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

    # Only substitute bracket markers in the body — never in the ## Evidence Citations tail,
    # which uses [n] as list indices, not citation markers.
    body, tail = _split_answer_for_inline_injection(answer)
    enriched_body = _INLINE_REF_TOKEN_RE.sub(replace_ref, body)
    enriched = f"{enriched_body.rstrip()}\n\n{tail.lstrip()}" if tail else enriched_body
    enriched = _inject_inline_citations(enriched, refs)
    enriched = _normalize_visible_inline_citations(enriched)

    if "class='citation'" in enriched or 'class="citation"' in enriched:
        return enriched

    if not refs:
        return enriched

    fallback_refs = " ".join([_citation_anchor(ref) for ref in refs[: min(3, len(refs))] if _citation_anchor(ref)])
    return _normalize_visible_inline_citations(f"{enriched}\n\nEvidence: {fallback_refs}")
