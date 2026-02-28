from __future__ import annotations

from typing import Any

from .constants import NUMBER_RE
from .text_utils import compact, contains_negation, tokenize


def detect_potential_contradictions(evidence_units: list[dict[str, str]]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    limited = evidence_units[:12]
    for left_idx in range(len(limited)):
        left = limited[left_idx]
        left_text = str(left.get("text") or "")
        left_tokens = tokenize(left_text)
        if len(left_tokens) < 4:
            continue
        left_numbers = NUMBER_RE.findall(left_text)
        left_negation = contains_negation(left_text)
        for right_idx in range(left_idx + 1, len(limited)):
            right = limited[right_idx]
            right_text = str(right.get("text") or "")
            right_tokens = tokenize(right_text)
            if len(right_tokens) < 4:
                continue
            overlap = left_tokens.intersection(right_tokens)
            if len(overlap) < 4:
                continue
            right_numbers = NUMBER_RE.findall(right_text)
            right_negation = contains_negation(right_text)
            contradiction_reason = ""
            if left_negation != right_negation and len(overlap) >= 5:
                contradiction_reason = "negation_mismatch"
            elif left_numbers and right_numbers and left_numbers[0] != right_numbers[0] and len(overlap) >= 5:
                contradiction_reason = "numeric_mismatch"
            if not contradiction_reason:
                continue
            contradictions.append(
                {
                    "type": contradiction_reason,
                    "left_source": str(left.get("source") or ""),
                    "right_source": str(right.get("source") or ""),
                    "overlap_terms": sorted(list(overlap))[:8],
                    "left_excerpt": compact(left_text, 180),
                    "right_excerpt": compact(right_text, 180),
                }
            )
            if len(contradictions) >= 6:
                return contradictions
    return contradictions
