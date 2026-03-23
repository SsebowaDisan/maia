from __future__ import annotations

"""Backward-compatible re-export shim.

All report-generation logic has been split into focused modules:
  - report_utils.py            primitives, constants, normalization, highlights, references
  - report_llm_intent.py       intent classification, location signal, QA, preferences
  - report_llm_content.py      executive summary, analysis, next steps, composer, contradictions
  - report_analytics_sections.py  GA4 data sections (template for SAP, Salesforce, etc.)

To add a new data source (e.g. SAP):
  1. Create report_sap_sections.py following the same pattern as report_analytics_sections.py.
  2. Implement section_lines / insight_highlights / insight_paragraphs guarded on their settings key.
  3. Re-export the new functions here and wire them into data_tools.py.
"""

from api.services.agent.tools.report_analytics_sections import (
    _analytics_insight_highlights,
    _analytics_insight_paragraphs,
    _analytics_section_lines,
)
from api.services.agent.tools.report_evidence_digest import (
    _annotated_source_lines,
    _build_evidence_findings_with_llm,
    _evidence_findings_markdown,
)
from api.services.agent.tools.report_llm_content import (
    _analysis_paragraphs_with_llm,
    _compose_executive_summary,
    _contradiction_section_lines,
    _detect_source_contradictions,
    _draft_report_markdown_with_llm,
    _fallback_analysis_paragraphs,
    _recommended_next_steps_with_llm,
)
from api.services.agent.tools.report_llm_intent import (
    _classify_report_intent_with_llm,
    _draft_direct_answer,
    _extract_location_signal_with_llm,
    _prefers_simple_explanation,
)
from api.services.agent.tools.report_utils import (
    EMAIL_RE,
    REQUEST_STYLE_RE,
    SCENE_SURFACE_SYSTEM,
    STOPWORDS,
    THEME_KEYWORDS,
    WORD_RE,
    _as_float,
    _auto_highlights_from_sources,
    _coerce_bool,
    _event,
    _first_sentence,
    _normalize_source_rows,
    _redact_delivery_targets,
    _reference_lines,
    _report_delivery_targets,
    _simple_explanation_lines,
    _theme_examples,
    _topic_label,
    _top_terms_from_sources,
)

__all__ = [
    # report_utils
    "EMAIL_RE",
    "REQUEST_STYLE_RE",
    "SCENE_SURFACE_SYSTEM",
    "STOPWORDS",
    "THEME_KEYWORDS",
    "WORD_RE",
    "_as_float",
    "_auto_highlights_from_sources",
    "_coerce_bool",
    "_event",
    "_first_sentence",
    "_normalize_source_rows",
    "_redact_delivery_targets",
    "_reference_lines",
    "_report_delivery_targets",
    "_simple_explanation_lines",
    "_theme_examples",
    "_topic_label",
    "_top_terms_from_sources",
    # report_llm_intent
    "_classify_report_intent_with_llm",
    "_draft_direct_answer",
    "_extract_location_signal_with_llm",
    "_prefers_simple_explanation",
    # report_llm_content
    "_analysis_paragraphs_with_llm",
    "_compose_executive_summary",
    "_contradiction_section_lines",
    "_detect_source_contradictions",
    "_draft_report_markdown_with_llm",
    "_fallback_analysis_paragraphs",
    "_recommended_next_steps_with_llm",
    # report_analytics_sections
    "_analytics_insight_highlights",
    "_analytics_insight_paragraphs",
    "_analytics_section_lines",
    "_annotated_source_lines",
    "_build_evidence_findings_with_llm",
    "_evidence_findings_markdown",
]
