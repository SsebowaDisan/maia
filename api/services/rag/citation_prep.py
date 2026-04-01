"""RAG Pipeline Phase 8: Citation Prep — build precise jump targets for every chunk.

Runs AFTER indexing (Phase 7). For each chunk we create CitationAnchors that
tell the frontend exactly how to highlight the source evidence:

  - EXACT tier: chunk has EvidenceSpans with BoundingBoxes → pixel-level highlight
  - PAGE tier:  chunk has page info but no bbox → jump to page
  - SNIPPET tier: chunk has text but no geometry → fuzzy text match in viewer
  - For URL chunks: SNIPPET with url_fragment built from heading/paragraph

The citation lookup is stored module-level so retrieval (Phase 9+) can attach
anchors without re-computing. RAG remains usable while this phase runs because
retrieval can proceed with or without anchors.

ONLY this phase sets source.citation_ready = True.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from api.services.rag.types import (
    BoundingBox,
    Chunk,
    CitationAnchor,
    CitationTier,
    ExtractionResult,
    EvidenceSpan,
    SourceRecord,
    SourceType,
)

logger = logging.getLogger(__name__)

# ── Module-level citation anchor store ──────────────────────────────────────

# chunk_id → list[CitationAnchor]
_ANCHOR_STORE: dict[str, list[CitationAnchor]] = {}


def get_anchors(chunk_id: str) -> list[CitationAnchor]:
    """Retrieve precomputed citation anchors for a chunk. Returns [] if not ready."""
    return _ANCHOR_STORE.get(chunk_id, [])


def clear_anchors() -> None:
    """Clear anchor store. Useful for tests."""
    _ANCHOR_STORE.clear()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _heading_to_fragment(heading_path: list[str]) -> str:
    """Convert a heading path to a URL fragment (GitHub-style slug)."""
    if not heading_path:
        return ""
    heading = heading_path[-1]
    slug = re.sub(r"[^\w\s-]", "", heading.lower())
    slug = re.sub(r"[\s]+", "-", slug.strip())
    return slug


def _build_anchor_from_span(
    span: EvidenceSpan,
    chunk: Chunk,
    is_url_source: bool,
) -> CitationAnchor:
    """Create a single CitationAnchor from an EvidenceSpan."""
    # EXACT: span has a bounding box with real geometry
    if span.bbox and span.bbox.width > 0 and span.bbox.height > 0:
        return CitationAnchor(
            source_id=chunk.source_id,
            chunk_id=chunk.id,
            page=span.page,
            tier=CitationTier.EXACT,
            bbox=span.bbox,
            text_snippet=span.text[:200] if span.text else "",
            paragraph_index=span.paragraph_index,
            heading_path=list(span.heading_path),
        )

    # PAGE: span has page info but no bbox
    if span.page >= 0 and not is_url_source:
        return CitationAnchor(
            source_id=chunk.source_id,
            chunk_id=chunk.id,
            page=span.page,
            tier=CitationTier.PAGE,
            text_snippet=span.text[:200] if span.text else "",
            heading_path=list(span.heading_path),
        )

    # SNIPPET for URL sources: use paragraph_index or heading as url_fragment
    if is_url_source:
        fragment = ""
        if span.heading_path:
            fragment = _heading_to_fragment(span.heading_path)
        elif span.paragraph_index >= 0:
            fragment = f"p-{span.paragraph_index}"
        return CitationAnchor(
            source_id=chunk.source_id,
            chunk_id=chunk.id,
            page=0,
            tier=CitationTier.SNIPPET,
            text_snippet=span.text[:200] if span.text else "",
            paragraph_index=span.paragraph_index,
            heading_path=list(span.heading_path),
            url_fragment=fragment,
        )

    # SNIPPET fallback: text only, no geometry
    return CitationAnchor(
        source_id=chunk.source_id,
        chunk_id=chunk.id,
        page=span.page if span.page >= 0 else 0,
        tier=CitationTier.SNIPPET,
        text_snippet=span.text[:200] if span.text else "",
        heading_path=list(span.heading_path),
    )


def _build_chunk_fallback_anchor(chunk: Chunk, is_url_source: bool) -> CitationAnchor:
    """Build a fallback anchor when the chunk has no individual spans."""
    if is_url_source:
        fragment = _heading_to_fragment(chunk.heading_path)
        return CitationAnchor(
            source_id=chunk.source_id,
            chunk_id=chunk.id,
            page=0,
            tier=CitationTier.SNIPPET,
            text_snippet=chunk.text[:200],
            heading_path=list(chunk.heading_path),
            url_fragment=fragment,
        )

    if chunk.page_start >= 0:
        return CitationAnchor(
            source_id=chunk.source_id,
            chunk_id=chunk.id,
            page=chunk.page_start,
            tier=CitationTier.PAGE,
            text_snippet=chunk.text[:200],
            heading_path=list(chunk.heading_path),
        )

    return CitationAnchor(
        source_id=chunk.source_id,
        chunk_id=chunk.id,
        page=0,
        tier=CitationTier.SNIPPET,
        text_snippet=chunk.text[:200],
        heading_path=list(chunk.heading_path),
    )


# ── Public API ──────────────────────────────────────────────────────────────

async def prepare_citations(
    source: SourceRecord,
    chunks: list[Chunk],
    extraction: ExtractionResult,
) -> list[CitationAnchor]:
    """Phase 8: Build CitationAnchors for every chunk of a source.

    For each chunk, inspects its EvidenceSpans to determine the best citation
    tier (EXACT > PAGE > SNIPPET). Stores results in the module-level anchor
    store so retrieval phases can attach them later.

    Parameters
    ----------
    source : the source record being prepared
    chunks : all chunks belonging to this source (post-indexing)
    extraction : the extraction result (used for extra context if needed)

    Returns
    -------
    Flat list of all CitationAnchors created across all chunks.
    """
    is_url = source.source_type == SourceType.URL
    all_anchors: list[CitationAnchor] = []

    for idx, chunk in enumerate(chunks):
        chunk_anchors: list[CitationAnchor] = []

        if chunk.spans:
            # Build an anchor for each evidence span in the chunk
            for span in chunk.spans:
                anchor = _build_anchor_from_span(span, chunk, is_url)
                chunk_anchors.append(anchor)
        else:
            # No spans — build a single fallback anchor from the chunk itself
            chunk_anchors.append(_build_chunk_fallback_anchor(chunk, is_url))

        _ANCHOR_STORE[chunk.id] = chunk_anchors
        # Retrieval chunk IDs come from the index layer ("{source_id}::{i}").
        # Keep an alias so citation anchors resolve after indexing.
        index_alias = f"{source.id}::{idx}"
        _ANCHOR_STORE[index_alias] = chunk_anchors
        all_anchors.extend(chunk_anchors)

    logger.info(
        "Citation prep: %d anchors for %d chunks of source %s (tiers: %s)",
        len(all_anchors),
        len(chunks),
        source.id,
        _summarize_tiers(all_anchors),
    )

    return all_anchors


def _summarize_tiers(anchors: list[CitationAnchor]) -> str:
    """Return a compact tier summary like 'EXACT=3, PAGE=7, SNIPPET=2'."""
    counts: dict[str, int] = {}
    for a in anchors:
        tier_name = a.tier.value if hasattr(a.tier, "value") else str(a.tier)
        counts[tier_name] = counts.get(tier_name, 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))


async def mark_citation_ready(source: SourceRecord) -> None:
    """ONLY this phase sets source.citation_ready = True."""
    source.citation_ready = True
    source.updated_at = datetime.now(timezone.utc).isoformat()
    logger.info("Source %s marked citation_ready", source.id)
