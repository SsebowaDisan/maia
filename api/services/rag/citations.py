"""RAG Pipeline Phase 13: Citations — build renderable citation objects.

Takes the GeneratedAnswer (with [ref] markers and bound claims) and the
ranked evidence, then creates Citation objects the UI can render:

  - PDF citations: include BoundingBox list for highlight overlays
  - URL citations: include url_fragment for jump-to-section
  - All citations: include tier, snippet, source info, credibility
"""

from __future__ import annotations

import logging

from api.services.rag.types import (
    BoundingBox,
    Citation,
    CitationAnchor,
    CitationTier,
    GeneratedAnswer,
    RankedEvidence,
    SourceType,
)
from api.services.rag.config import classify_credibility

logger = logging.getLogger(__name__)


def _best_anchor(anchors: list[CitationAnchor]) -> CitationAnchor | None:
    """Pick the highest-tier anchor from a list.

    Priority: EXACT > PAGE > SNIPPET > FALLBACK.
    """
    if not anchors:
        return None

    tier_priority = {
        CitationTier.EXACT: 0,
        CitationTier.PAGE: 1,
        CitationTier.SNIPPET: 2,
        CitationTier.FALLBACK: 3,
    }
    return min(anchors, key=lambda a: tier_priority.get(a.tier, 99))


def _collect_highlight_boxes(anchors: list[CitationAnchor]) -> list[BoundingBox]:
    """Gather bounding boxes for highlighting.

    Only return the BEST anchor's bbox — not all of them.
    Highlighting every text block in a chunk covers the entire page
    and makes the highlight useless. Instead, pick the single best
    anchor (the one _best_anchor would choose) so the highlight
    focuses on the most relevant evidence passage.
    """
    best = _best_anchor(anchors)
    if best and best.tier == CitationTier.EXACT and best.bbox:
        return [best.bbox]
    # If no EXACT anchor, return nothing — page-level jump is enough
    return []


def _get_url_info(anchors: list[CitationAnchor]) -> tuple[str, int]:
    """Extract url_fragment and paragraph_index from anchors for URL citations."""
    for anchor in anchors:
        if anchor.url_fragment:
            return anchor.url_fragment, anchor.paragraph_index
    # Fall back to first anchor with paragraph_index
    for anchor in anchors:
        if anchor.paragraph_index >= 0:
            return "", anchor.paragraph_index
    return "", -1


def _determine_page(anchors: list[CitationAnchor], chunk_page: int) -> int:
    """Get the best page number from anchors, falling back to chunk page."""
    for anchor in anchors:
        if anchor.tier in (CitationTier.EXACT, CitationTier.PAGE) and anchor.page >= 0:
            return anchor.page
    return max(chunk_page, 0)


def _determine_tier(anchors: list[CitationAnchor]) -> CitationTier:
    """Determine the overall citation tier from available anchors."""
    best = _best_anchor(anchors)
    if best:
        return best.tier
    return CitationTier.FALLBACK


# ── Public API ──────────────────────────────────────────────────────────────

async def build_citations(
    answer: GeneratedAnswer,
    evidence: list[RankedEvidence],
) -> list[Citation]:
    """Phase 13: Build renderable Citation objects from the answer and evidence.

    For each [ref_id] referenced in the answer:
      1. Find the evidence it points to (1-indexed).
      2. Get the CitationAnchors for that evidence chunk.
      3. Create a Citation with tier, highlight boxes, page, snippet, etc.

    Parameters
    ----------
    answer : the generated answer with [ref] markers and parsed claims
    evidence : ranked evidence from Phase 10

    Returns
    -------
    List of Citation objects sorted by ref_id order.
    """
    # Collect all referenced ref_ids from claims
    referenced_ids: set[int] = set()
    for claim in answer.claims:
        for ref_str in claim.ref_ids:
            # Parse "[N]" to integer N
            try:
                num = int(ref_str.strip("[]"))
                referenced_ids.add(num)
            except ValueError:
                continue

    citations: list[Citation] = []

    for ref_num in sorted(referenced_ids):
        idx = ref_num - 1  # evidence is 0-indexed, refs are 1-indexed
        if idx < 0 or idx >= len(evidence):
            logger.warning("Reference [%d] out of range (evidence count: %d)", ref_num, len(evidence))
            continue

        ev = evidence[idx]
        chunk = ev.chunk
        anchors = ev.anchors

        # Determine citation properties
        tier = _determine_tier(anchors)
        page = _determine_page(anchors, chunk.page_start)
        highlight_boxes = _collect_highlight_boxes(anchors)
        best = _best_anchor(anchors)
        if best is None:
            # Keep a stable chunk-level jump target even when citation prep anchors
            # are unavailable (for example, after process restart).
            best = CitationAnchor(
                source_id=chunk.source_id,
                chunk_id=chunk.id,
                page=max(chunk.page_start, 0),
                tier=CitationTier.PAGE if chunk.page_start >= 0 else CitationTier.FALLBACK,
                text_snippet=chunk.text[:200],
                heading_path=list(chunk.heading_path),
            )
        snippet = best.text_snippet if best.text_snippet else chunk.text[:300]

        # Source info
        source_name = chunk.filename or chunk.source_id
        source_type_str = chunk.source_type
        try:
            source_type = SourceType(source_type_str)
        except (ValueError, KeyError):
            source_type = SourceType.UNKNOWN

        # URL info
        url = chunk.metadata.get("url", "")
        url_fragment, para_idx = _get_url_info(anchors)

        # Credibility
        cred_source = url or source_name
        credibility = classify_credibility(cred_source)

        citation = Citation(
            ref_id=f"[{ref_num}]",
            source_id=chunk.source_id,
            source_name=source_name,
            source_type=source_type,
            page=page,
            tier=tier,
            snippet=snippet,
            anchor=best,
            highlight_boxes=highlight_boxes,
            url=url,
            url_fragment=url_fragment,
            paragraph_index=para_idx,
            credibility=credibility,
            relevance_score=ev.final_score,
        )
        citations.append(citation)

    logger.info(
        "Built %d citations (tiers: %s)",
        len(citations),
        _summarize_tiers(citations),
    )

    return citations


def _summarize_tiers(citations: list[Citation]) -> str:
    """Return a compact tier summary."""
    counts: dict[str, int] = {}
    for c in citations:
        tier_name = c.tier.value if hasattr(c.tier, "value") else str(c.tier)
        counts[tier_name] = counts.get(tier_name, 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
