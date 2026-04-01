"""RAG Pipeline Phase 14: Deliver — assemble the final payload for the UI.

Builds the DeliveryPayload that contains everything the frontend needs:
  - The generated answer with inline citations
  - Citation objects with highlight geometry
  - Evidence panel cards grouped by source
  - Warnings for low confidence, conflicts, partial coverage, etc.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from api.services.rag.types import (
    Citation,
    CoverageVerdict,
    DeliveryPayload,
    EvidenceCard,
    GeneratedAnswer,
    RankedEvidence,
    SourceType,
)

logger = logging.getLogger(__name__)


def _build_evidence_cards(
    evidence: list[RankedEvidence],
    citations: list[Citation],
) -> list[EvidenceCard]:
    """Build evidence panel cards, one per cited evidence chunk.

    Cards are grouped by source file so the UI can render them under
    source headings. Each card includes the snippet, highlight boxes,
    relevance score, and which citation it supports.
    """
    # Map ref_id → citation for cross-referencing
    ref_to_citation: dict[str, Citation] = {}
    for cit in citations:
        ref_to_citation[cit.ref_id] = cit

    # Map chunk_id → ref_id from citations
    chunk_to_ref: dict[str, str] = {}
    for cit in citations:
        chunk_to_ref[cit.source_id] = cit.ref_id

    cards: list[EvidenceCard] = []
    seen_chunks: set[str] = set()

    for i, ev in enumerate(evidence):
        if ev.chunk.id in seen_chunks:
            continue
        seen_chunks.add(ev.chunk.id)

        chunk = ev.chunk
        ref_id = f"[{i + 1}]"

        # Get highlight boxes from corresponding citation if available
        highlight_boxes = []
        if ref_id in ref_to_citation:
            highlight_boxes = list(ref_to_citation[ref_id].highlight_boxes)

        source_name = chunk.filename or chunk.source_id
        try:
            source_type = SourceType(chunk.source_type)
        except (ValueError, KeyError):
            source_type = SourceType.UNKNOWN

        card = EvidenceCard(
            source_id=chunk.source_id,
            source_name=source_name,
            source_type=source_type,
            page=chunk.page_start,
            snippet=chunk.text[:500],
            relevance_score=ev.final_score,
            highlight_boxes=highlight_boxes,
            heading_path=list(chunk.heading_path),
            ref_id=ref_id,
        )
        cards.append(card)

    # Sort cards by source then page for clean grouping
    cards.sort(key=lambda c: (c.source_name, c.page))

    return cards


def _build_warnings(
    answer: GeneratedAnswer,
    evidence: list[RankedEvidence],
    citations: list[Citation],
) -> list[str]:
    """Generate user-facing warnings based on answer quality signals."""
    warnings: list[str] = []

    # Low confidence evidence
    low_conf = [ev for ev in evidence if ev.final_score < 0.5]
    if low_conf:
        count = len(low_conf)
        warnings.append(
            f"Low confidence evidence: {count} of {len(evidence)} "
            f"sources scored below 0.5 relevance."
        )

    # Coverage warnings
    if answer.coverage:
        verdict = answer.coverage.verdict
        if verdict == CoverageVerdict.PARTIAL:
            missing = ", ".join(answer.coverage.missing_aspects[:3])
            warnings.append(
                f"Partial coverage: the evidence may not fully address: {missing}"
            )
        elif verdict == CoverageVerdict.CONFLICTING:
            conflict_count = len(answer.coverage.conflicts)
            warnings.append(
                f"Conflicting sources: {conflict_count} factual "
                f"disagreement(s) detected between sources."
            )
        elif verdict == CoverageVerdict.INSUFFICIENT:
            warnings.append(
                "Insufficient evidence: the available sources do not "
                "adequately address this question."
            )
        elif verdict == CoverageVerdict.MATH_INCOMPLETE:
            missing_vars = ", ".join(answer.coverage.math_missing[:5])
            warnings.append(
                f"Calculation inputs incomplete: missing values for: {missing_vars}"
            )

    # Grounding warning
    if not answer.grounded:
        warnings.append(
            "Some claims in the answer may not be fully supported by "
            "the provided evidence."
        )

    return warnings


# ── Public API ──────────────────────────────────────────────────────────────

async def deliver(
    answer: GeneratedAnswer,
    citations: list[Citation],
    evidence: list[RankedEvidence],
    scope_description: str = "",
    trace_id: str = "",
) -> DeliveryPayload:
    """Phase 14: Assemble the final delivery payload for the UI.

    Combines the answer, citations, evidence cards, and warnings into
    a single DeliveryPayload that the frontend can render directly.

    Parameters
    ----------
    answer : generated answer from Phase 12
    citations : citation objects from Phase 13
    evidence : ranked evidence from Phase 10
    scope_description : human-readable scope (e.g. "group:marketing_docs")
    trace_id : correlation ID for the pipeline run

    Returns
    -------
    DeliveryPayload with everything the UI needs.
    """
    # Build evidence panel cards
    evidence_cards = _build_evidence_cards(evidence, citations)

    # Build warnings
    warnings = _build_warnings(answer, evidence, citations)

    payload = DeliveryPayload(
        answer=answer,
        citations=citations,
        evidence_panel=evidence_cards,
        search_scope=scope_description,
        warnings=warnings,
        trace_id=trace_id,
    )

    logger.info(
        "Deliver: %d citations, %d evidence cards, %d warnings, trace=%s",
        len(citations),
        len(evidence_cards),
        len(warnings),
        trace_id,
    )

    return payload
