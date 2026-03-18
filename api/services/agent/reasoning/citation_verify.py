"""Citation Verification — validates that sources referenced in agent output actually exist.

Inspired by AutoResearchClaw's three-layer verification pipeline.
Checks cited URLs, document names, and claims against the RAG index
and web sources to flag hallucinated citations.

Usage:
    results = verify_citations(text="The report states... [Source: Q3 Report.pdf, p.12]", rag_search=my_search_fn)
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Citation extraction ───────────────────────────────────────────────────────

_CITATION_PATTERNS = [
    re.compile(r"\[Source:\s*(.+?)(?:,\s*p\.?\s*(\d+))?\]", re.IGNORECASE),
    re.compile(r"\(Source:\s*(.+?)(?:,\s*p\.?\s*(\d+))?\)", re.IGNORECASE),
    re.compile(r"\[(\d+)\]\s*(.+?)(?:\.|$)"),
    re.compile(r"According to (.+?)[,.]"),
    re.compile(r"as (?:stated|reported|noted|mentioned) in (.+?)[,.]", re.IGNORECASE),
]


def extract_citations(text: str) -> list[dict[str, str]]:
    """Extract citation references from text."""
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            source = str(groups[0] or "").strip()
            page = str(groups[1] or "").strip() if len(groups) > 1 else ""
            if not source or len(source) < 3 or len(source) > 200:
                continue
            key = _normalize_title(source)
            if key in seen:
                continue
            seen.add(key)
            citations.append({"source": source, "page": page, "raw": match.group(0)})
    return citations


# ── Verification ──────────────────────────────────────────────────────────────

VERIFIED = "verified"
SUSPICIOUS = "suspicious"
HALLUCINATED = "hallucinated"
SKIPPED = "skipped"

_VERIFY_CACHE: dict[str, dict[str, Any]] = {}


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    return re.sub(r"[^a-z0-9\s]", "", title.lower()).strip()


def _cache_key(source: str) -> str:
    return hashlib.sha256(_normalize_title(source).encode()).hexdigest()[:16]


def _title_similarity(a: str, b: str) -> float:
    """Simple similarity: Jaccard on word sets."""
    words_a = set(_normalize_title(a).split())
    words_b = set(_normalize_title(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def verify_citations(
    text: str,
    *,
    rag_search: Callable[[str, int], list[dict[str, Any]]] | None = None,
    uploaded_filenames: list[str] | None = None,
    threshold_verified: float = 0.80,
    threshold_suspicious: float = 0.50,
) -> list[dict[str, Any]]:
    """Verify all citations found in text.

    Three-layer verification:
    L1: Check against uploaded file names (exact/fuzzy match)
    L2: Check against RAG index (semantic search)
    L3: Flag unverifiable citations

    Args:
        text: The text containing citations to verify.
        rag_search: Optional function(query, top_k) -> list[dict] for RAG lookup.
        uploaded_filenames: List of filenames in the user's knowledge base.
        threshold_verified: Similarity score for "verified" classification.
        threshold_suspicious: Similarity score for "suspicious" classification.

    Returns:
        List of verification results with status, score, and matched source.
    """
    citations = extract_citations(text)
    if not citations:
        return []

    filenames = [str(f) for f in (uploaded_filenames or [])]
    results: list[dict[str, Any]] = []

    for citation in citations:
        source = citation["source"]
        ck = _cache_key(source)

        if ck in _VERIFY_CACHE:
            results.append(_VERIFY_CACHE[ck])
            continue

        result = _verify_single(
            source=source,
            page=citation.get("page", ""),
            raw=citation.get("raw", ""),
            filenames=filenames,
            rag_search=rag_search,
            threshold_verified=threshold_verified,
            threshold_suspicious=threshold_suspicious,
        )
        _VERIFY_CACHE[ck] = result
        results.append(result)

    return results


def _verify_single(
    *,
    source: str,
    page: str,
    raw: str,
    filenames: list[str],
    rag_search: Callable[[str, int], list[dict[str, Any]]] | None,
    threshold_verified: float,
    threshold_suspicious: float,
) -> dict[str, Any]:
    """Verify a single citation through three layers."""
    base = {"source": source, "page": page, "raw": raw}

    # L1: Check against uploaded filenames
    for fname in filenames:
        sim = _title_similarity(source, fname)
        if sim >= threshold_verified:
            return {**base, "status": VERIFIED, "score": round(sim, 3), "matched": fname, "layer": "L1_filename"}

    # L2: Check against RAG index
    if rag_search:
        try:
            hits = rag_search(source, 3)
            for hit in hits:
                hit_source = str(hit.get("source", "") or hit.get("file_name", ""))
                hit_text = str(hit.get("text", ""))[:200]
                sim = max(
                    _title_similarity(source, hit_source),
                    _title_similarity(source, hit_text),
                )
                if sim >= threshold_verified:
                    return {**base, "status": VERIFIED, "score": round(sim, 3), "matched": hit_source or hit_text[:60], "layer": "L2_rag"}
                if sim >= threshold_suspicious:
                    return {**base, "status": SUSPICIOUS, "score": round(sim, 3), "matched": hit_source or hit_text[:60], "layer": "L2_rag"}
        except Exception as exc:
            logger.debug("RAG verification failed for '%s': %s", source, exc)

    # L3: Unverifiable — likely hallucinated
    # Check if it looks like a real document (has file extension)
    if re.search(r"\.\w{2,4}$", source):
        return {**base, "status": SUSPICIOUS, "score": 0.3, "matched": "", "layer": "L3_heuristic"}

    return {**base, "status": HALLUCINATED, "score": 0.0, "matched": "", "layer": "L3_unverifiable"}


def citation_integrity_score(results: list[dict[str, Any]]) -> float:
    """Compute overall citation integrity score (0.0 to 1.0)."""
    if not results:
        return 1.0
    verified = sum(1 for r in results if r["status"] == VERIFIED)
    return round(verified / len(results), 3)


def strip_hallucinated_citations(text: str, results: list[dict[str, Any]]) -> str:
    """Remove hallucinated citation markers from text."""
    cleaned = text
    for result in results:
        if result["status"] == HALLUCINATED and result.get("raw"):
            cleaned = cleaned.replace(result["raw"], "")
    return cleaned
