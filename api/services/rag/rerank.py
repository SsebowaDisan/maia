"""RAG Pipeline Phase 10: Rerank — score, deduplicate, and rank evidence.

Takes the raw retrieval hits and applies a multi-signal scoring formula:
    final_score = relevance * w_rel + credibility * w_cred + diversity * w_div

Credibility is based on source domain/type (arxiv > reddit).
Diversity penalizes clusters of chunks from the same page/source.
Near-duplicate chunks (>80% text overlap) are suppressed.
"""

from __future__ import annotations

import logging
from collections import Counter

from api.services.rag.types import (
    RAGConfig,
    RankedEvidence,
    RetrievedEvidence,
    SourceType,
)
from api.services.rag.config import classify_credibility

logger = logging.getLogger(__name__)


# ── Duplicate detection ─────────────────────────────────────────────────────

def _text_overlap(a: str, b: str) -> float:
    """Compute Jaccard overlap between two text strings at the word level.
    Returns a value in [0, 1]. 1.0 means identical word sets.
    """
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


def _is_near_duplicate(text: str, seen_texts: list[str], threshold: float = 0.80) -> bool:
    """Check if text is a near-duplicate of any previously seen text."""
    for seen in seen_texts:
        if _text_overlap(text, seen) > threshold:
            return True
    return False


# ── Credibility scoring ─────────────────────────────────────────────────────

def _credibility_score(evidence: RetrievedEvidence) -> float:
    """Score credibility based on source type and metadata.

    PDF from known publishers → high (0.9)
    Recognized medium sources → medium (0.6)
    Low-quality domains → low (0.3)
    Unknown / local files → neutral (0.5)
    """
    chunk = evidence.chunk

    # Check URL or filename for domain credibility
    url = chunk.metadata.get("url", "") or chunk.filename or ""
    tier = classify_credibility(url)

    tier_scores = {
        "high": 0.9,
        "medium": 0.6,
        "low": 0.3,
        "unknown": 0.5,
    }
    base = tier_scores.get(tier, 0.5)

    # Boost PDFs slightly (structured documents tend to be more reliable)
    if chunk.source_type == SourceType.PDF.value:
        base = min(1.0, base + 0.05)

    return base


# ── Diversity scoring ───────────────────────────────────────────────────────

def _compute_diversity_bonuses(evidence_list: list[RetrievedEvidence]) -> list[float]:
    """Compute diversity bonus for each evidence piece.

    Penalizes chunks that cluster on the same source+page. The first chunk
    from each source/page gets full bonus; subsequent ones get progressively less.
    """
    bonuses: list[float] = []
    seen: Counter[str] = Counter()

    for ev in evidence_list:
        key = f"{ev.chunk.source_id}::{ev.chunk.page_start}"
        count = seen[key]
        seen[key] += 1

        if count == 0:
            bonuses.append(1.0)       # first from this page: full bonus
        elif count == 1:
            bonuses.append(0.5)       # second: half
        else:
            bonuses.append(0.2)       # third+: minimal

    return bonuses


# ── Public API ──────────────────────────────────────────────────────────────

async def rerank(
    evidence: list[RetrievedEvidence],
    query: str,
    config: RAGConfig,
) -> list[RankedEvidence]:
    """Phase 10: Rerank retrieved evidence with multi-signal scoring.

    Steps:
      1. Suppress near-duplicate chunks (>80% word overlap).
      2. Score each piece: relevance (retrieval score), credibility, diversity.
      3. Compute final_score = relevance * 0.7 + credibility * 0.2 + diversity * 0.1
         (weights are configurable via RAGConfig).
      4. Sort by final_score descending.
      5. Return top config.final_k results.

    Parameters
    ----------
    evidence : raw retrieval results from Phase 9
    query : the original user query (reserved for future model reranking)
    config : pipeline configuration

    Returns
    -------
    Top-k RankedEvidence sorted by final_score descending.
    """
    if not evidence:
        return []

    # ── Step 1: Suppress near-duplicates ────────────────────────────────
    deduped: list[RetrievedEvidence] = []
    seen_texts: list[str] = []

    for ev in evidence:
        if _is_near_duplicate(ev.chunk.text, seen_texts):
            logger.debug("Suppressed near-duplicate chunk %s", ev.chunk.id)
            continue
        deduped.append(ev)
        seen_texts.append(ev.chunk.text)

    if len(deduped) < len(evidence):
        logger.info(
            "Deduplication: %d → %d evidence chunks",
            len(evidence), len(deduped),
        )

    # ── Step 2: Score each piece ────────────────────────────────────────
    # Normalize retrieval scores to 0-1 if needed
    max_retrieval = max((ev.score for ev in deduped), default=1.0)
    if max_retrieval <= 0:
        max_retrieval = 1.0

    credibility_scores = [_credibility_score(ev) for ev in deduped]
    diversity_bonuses = _compute_diversity_bonuses(deduped)

    # Weight configuration
    w_rel = 1.0 - config.credibility_weight - config.diversity_weight
    w_cred = config.credibility_weight
    w_div = config.diversity_weight

    # ── Step 3: Compute final scores and build RankedEvidence ───────────
    ranked: list[RankedEvidence] = []
    for i, ev in enumerate(deduped):
        rel = ev.score / max_retrieval
        cred = credibility_scores[i]
        div = diversity_bonuses[i]
        final = rel * w_rel + cred * w_cred + div * w_div

        ranked.append(
            RankedEvidence(
                chunk=ev.chunk,
                score=ev.score,
                match_type=ev.match_type,
                anchors=ev.anchors,
                rerank_score=rel,
                credibility_score=cred,
                diversity_bonus=div,
                final_score=final,
            )
        )

    # ── Step 4: Sort by final_score ─────────────────────────────────────
    ranked.sort(key=lambda r: r.final_score, reverse=True)

    # ── Step 5: Top-K ───────────────────────────────────────────────────
    result = ranked[: config.final_k] if config.final_k else ranked

    logger.info(
        "Reranked %d → %d evidence (top score=%.3f, bottom score=%.3f)",
        len(evidence),
        len(result),
        result[0].final_score if result else 0.0,
        result[-1].final_score if result else 0.0,
    )

    return result
