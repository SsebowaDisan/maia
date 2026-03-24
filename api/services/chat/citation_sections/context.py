from __future__ import annotations

import re
from typing import Any

from .shared import (
    _CONTEXT_TOKEN_STOPWORDS,
    _MIN_CONTEXT_MATCH_SCORE,
    _TOKEN_RE,
    _clean_text,
)

_PAGE_MENTION_RE = re.compile(
    r"\b(?:page|pages|p\.|pp\.)\s*([A-Za-z0-9]+)(?:\s*[-–]\s*([A-Za-z0-9]+))?",
    flags=re.IGNORECASE,
)


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


def _normalize_page_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    token = token.rstrip(".,;:)]}")
    token = token.lstrip("([{")
    return token


def _extract_page_mentions(text: str) -> set[str]:
    raw = str(text or "")
    if not raw:
        return set()
    values: set[str] = set()
    for match in _PAGE_MENTION_RE.finditer(raw):
        first = _normalize_page_token(match.group(1))
        second = _normalize_page_token(match.group(2))
        if first:
            values.add(first)
        if second:
            values.add(second)
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
            idx
            for idx in (
                raw.find(".", pivot_index, end),
                raw.find("!", pivot_index, end),
                raw.find("?", pivot_index, end),
            )
            if idx >= 0
        ]
        if sentence_end_candidates:
            end = min(sentence_end_candidates) + 1
    return _clean_text(raw[start:end])


def _best_ref_for_context(
    context: str,
    refs: list[dict[str, Any]],
) -> tuple[int | None, float]:
    raw_context = str(context or "")
    context_tokens = _tokens(context)
    if not context_tokens:
        context_tokens = set()
    context_pages = _extract_page_mentions(raw_context)
    if not context_tokens and not context_pages:
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
        page_label = _normalize_page_token(ref.get("page_label", ""))
        ref_tokens = _tokens(f"{phrase} {label} {source_name}")
        if not ref_tokens and not page_label:
            continue
        overlap_tokens = context_tokens & ref_tokens
        overlap = len(overlap_tokens)
        if overlap <= 0 and not context_pages:
            continue
        informative_overlap = sum(1 for token in overlap_tokens if _is_informative_token(token))
        if overlap < 2 and informative_overlap <= 0 and not context_pages:
            short_context_match = (
                len(context_tokens) <= 2
                and len(ref_tokens) <= 8
                and any(len(token) >= 4 for token in overlap_tokens)
            )
            if not short_context_match:
                continue
        precision = overlap / max(1, len(context_tokens)) if context_tokens else 0.0
        recall = overlap / max(1, len(ref_tokens)) if ref_tokens else 0.0
        score = (precision * 0.6) + (recall * 0.3)
        if informative_overlap > 0:
            score += 0.1 * min(1.0, informative_overlap / max(1, overlap))
        if context_pages:
            if page_label and page_label in context_pages:
                score += 0.45
            elif page_label:
                score -= 0.18
            else:
                score -= 0.08
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
    if "|" in fragment and fragment.count("|") >= 2:
        return False
    if re.fullmatch(r"[-=*#\s]+", normalized):
        return False
    trimmed = re.sub(r"^[-*â€¢\d\.\)\(\s]+", "", normalized)
    if len(trimmed) < 16:
        return False
    return True
