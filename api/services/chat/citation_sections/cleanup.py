from __future__ import annotations

import re

from .shared import (
    _CITATION_ANCHOR_OPEN_RE,
    _CITATION_ANCHOR_RE,
    _FAST_QA_NOISE_SECTION_SUBSTRINGS,
    _FAST_QA_NOISE_SECTION_TITLES,
    _HTML_TAG_RE,
    _INLINE_REF_TOKEN_RE,
    _SENTENCE_SEGMENT_RE,
    _TOP_LEVEL_MD_HEADING_RE,
    _clean_text,
    _split_answer_for_inline_injection,
)


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

    if len(cleaned_body) < 260:
        return text

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
