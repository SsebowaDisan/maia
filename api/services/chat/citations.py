from __future__ import annotations

from .citation_sections.injection import render_fast_citation_links
from .citation_sections.public_ops import (
    append_required_citation_suffix,
    enforce_required_citations,
    normalize_fast_answer,
)
from .citation_sections.refs import (
    assign_fast_source_refs,
    build_citation_quality_metrics,
    build_claim_signal_summary,
    build_source_usage,
    collect_cited_ref_ids,
    resolve_required_citation_mode,
)
from .citation_sections.resolution import build_fast_info_html
from .citation_sections.shared import (
    ALLOWED_CITATION_MODES,
    CITATION_MODE_FOOTNOTE,
    CITATION_MODE_INLINE,
    normalize_info_evidence_html,
)

__all__ = [
    "ALLOWED_CITATION_MODES",
    "CITATION_MODE_FOOTNOTE",
    "CITATION_MODE_INLINE",
    "append_required_citation_suffix",
    "assign_fast_source_refs",
    "build_citation_quality_metrics",
    "build_claim_signal_summary",
    "build_fast_info_html",
    "build_source_usage",
    "collect_cited_ref_ids",
    "enforce_required_citations",
    "normalize_fast_answer",
    "normalize_info_evidence_html",
    "render_fast_citation_links",
    "resolve_required_citation_mode",
]
