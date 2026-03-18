"""Novelty Check — detects if a research topic already exists in the knowledge base.

Inspired by AutoResearchClaw's novelty checker.
Before producing a research report, checks whether the RAG index or web
already contains substantially similar content. Prevents workflows from
producing reports that just restate existing knowledge.

Usage:
    result = check_novelty(
        topic="Q3 revenue analysis for ACME Corp",
        rag_search=my_search_fn,
    )
    if result["recommendation"] == "abort":
        print("This topic is already covered:", result["matched_sources"])
"""
from __future__ import annotations

import re
from typing import Any, Callable


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", text.lower()).strip()


def _word_set(text: str) -> set[str]:
    return set(_normalize(text).split())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sequence_overlap(a: str, b: str) -> float:
    """Longest common subsequence ratio."""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    m, n = len(na), len(nb)
    if m > 500 or n > 500:
        na, nb = na[:500], nb[:500]
        m, n = len(na), len(nb)
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if na[i - 1] == nb[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    lcs = prev[n]
    return (2 * lcs) / (m + n) if (m + n) > 0 else 0.0


def compute_similarity(topic: str, candidate: str) -> float:
    """Compute similarity: 70% keyword Jaccard + 30% sequence overlap."""
    jac = _jaccard(_word_set(topic), _word_set(candidate))
    seq = _sequence_overlap(topic, candidate)
    return round(0.7 * jac + 0.3 * seq, 4)


def check_novelty(
    *,
    topic: str,
    rag_search: Callable[[str, int], list[dict[str, Any]]] | None = None,
    existing_titles: list[str] | None = None,
    threshold_abort: float = 0.85,
    threshold_differentiate: float = 0.60,
    threshold_caution: float = 0.40,
    top_k: int = 10,
) -> dict[str, Any]:
    """Check whether a topic is novel relative to existing knowledge.

    Args:
        topic: The research topic or question.
        rag_search: Optional function(query, top_k) -> list[dict] for RAG lookup.
        existing_titles: Optional list of existing report/document titles.
        threshold_abort: Above this → topic already fully covered.
        threshold_differentiate: Above this → substantial overlap, needs angle.
        threshold_caution: Above this → some overlap, proceed with awareness.

    Returns:
        dict with: novelty_score, recommendation, matched_sources, details
    """
    candidates: list[dict[str, Any]] = []

    # Check against explicit titles
    for title in (existing_titles or []):
        sim = compute_similarity(topic, title)
        candidates.append({"source": title, "similarity": sim, "origin": "existing_title"})

    # Check against RAG index
    if rag_search:
        try:
            hits = rag_search(topic, top_k)
            for hit in hits:
                text = str(hit.get("text", ""))[:300]
                source = str(hit.get("source", ""))
                sim = compute_similarity(topic, text)
                title_sim = compute_similarity(topic, source) if source else 0.0
                best_sim = max(sim, title_sim)
                candidates.append({"source": source or text[:60], "similarity": best_sim, "origin": "rag"})
        except Exception:
            pass

    if not candidates:
        return {
            "novelty_score": 1.0,
            "recommendation": "proceed",
            "matched_sources": [],
            "details": "No existing content found — topic appears novel.",
        }

    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    top_sim = candidates[0]["similarity"]
    novelty_score = round(1.0 - top_sim, 4)

    if top_sim >= threshold_abort:
        recommendation = "abort"
        details = f"Topic is already covered (similarity {top_sim:.0%}). Consider a different angle or reviewing the existing content."
    elif top_sim >= threshold_differentiate:
        recommendation = "differentiate"
        details = f"Substantial overlap found ({top_sim:.0%}). Proceed but explicitly differentiate from existing content."
    elif top_sim >= threshold_caution:
        recommendation = "proceed_with_caution"
        details = f"Some overlap detected ({top_sim:.0%}). The topic has related existing content — ensure your analysis adds new value."
    else:
        recommendation = "proceed"
        details = f"Topic appears sufficiently novel (max overlap {top_sim:.0%})."

    matched = [c for c in candidates[:5] if c["similarity"] >= threshold_caution]

    return {
        "novelty_score": novelty_score,
        "recommendation": recommendation,
        "matched_sources": matched,
        "details": details,
    }
