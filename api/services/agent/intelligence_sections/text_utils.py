from __future__ import annotations

from .constants import NEGATION_TERMS, STOPWORDS, WORD_RE


def compact(text: str, max_len: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 1].rstrip()}..."


def tokenize(text: str) -> set[str]:
    words = [match.group(0).lower() for match in WORD_RE.finditer(str(text or ""))]
    return {word for word in words if word not in STOPWORDS and len(word) >= 4}


def contains_negation(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term in lowered.split() for term in NEGATION_TERMS)
