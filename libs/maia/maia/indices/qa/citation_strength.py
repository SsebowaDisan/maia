from decouple import config

from maia.base import Document

MAIA_CITATION_STRENGTH_ORDERING_ENABLED = config(
    "MAIA_CITATION_STRENGTH_ORDERING_ENABLED",
    False,
    cast=bool,
)
MAIA_CITATION_FUZZY_MATCH_ENABLED = config(
    "MAIA_CITATION_FUZZY_MATCH_ENABLED",
    True,
    cast=bool,
)
MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL = config(
    "MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL",
    0.5,
    cast=float,
)
MAIA_CITATION_STRENGTH_WEIGHT_LLM = config(
    "MAIA_CITATION_STRENGTH_WEIGHT_LLM",
    0.4,
    cast=float,
)
MAIA_CITATION_STRENGTH_WEIGHT_SPAN = config(
    "MAIA_CITATION_STRENGTH_WEIGHT_SPAN",
    0.1,
    cast=float,
)


def _safe_float(value) -> float:
    try:
        parsed = float(value)
    except Exception:
        return 0.0
    if parsed != parsed:
        return 0.0
    return parsed


def _compute_span_strength(*, doc: Document, span_text: str, is_exact_match: bool) -> float:
    metadata = getattr(doc, "metadata", {}) or {}
    retrieval = max(
        _safe_float(metadata.get("rerank_score", 0.0)),
        _safe_float(metadata.get("vector_score", 0.0)),
        min(1.0, _safe_float(metadata.get("score", 0.0)) / 25.0),
    )
    llm_score = min(1.0, max(0.0, _safe_float(metadata.get("llm_trulens_score", 0.0))))
    exact_bonus = 0.60 if is_exact_match else 0.0
    span_length_bonus = min(0.40, len(str(span_text or "")) / 900.0)
    span_bonus = min(1.0, exact_bonus + span_length_bonus)
    weighted = (
        retrieval * float(MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL)
        + llm_score * float(MAIA_CITATION_STRENGTH_WEIGHT_LLM)
        + span_bonus * float(MAIA_CITATION_STRENGTH_WEIGHT_SPAN)
    )
    return max(0.0, min(1.0, weighted))
