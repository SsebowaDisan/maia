"""RAG Pipeline Phase 15: Configuration — scoring weights, credibility tiers, defaults."""
from __future__ import annotations

# Load .env BEFORE reading any os.environ values at module level
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=False)
except ImportError:
    pass

from api.services.rag.types import RAGConfig

# ── Credibility tiers (matched against source URL domain or metadata) ───────

CREDIBILITY_HIGH: list[str] = [
    "arxiv.org",
    "nature.com",
    "science.org",
    "ieee.org",
    "acm.org",
    "gov",           # any .gov domain
    "edu",           # any .edu domain
    "nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "springer.com",
    "wiley.com",
    "cambridge.org",
]

CREDIBILITY_MEDIUM: list[str] = [
    "wikipedia.org",
    "medium.com",
    "stackoverflow.com",
    "docs.python.org",
    "developer.mozilla.org",
    "microsoft.com",
    "github.com",
    "docs.aws.amazon.com",
]

CREDIBILITY_LOW: list[str] = [
    "reddit.com",
    "quora.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "tiktok.com",
    "yahoo.com",
]

# ── Scoring weight presets ──────────────────────────────────────────────────

WEIGHT_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {
        "hybrid_weight": 0.7,
        "credibility_weight": 0.2,
        "diversity_weight": 0.1,
    },
    "precision": {
        "hybrid_weight": 0.85,
        "credibility_weight": 0.1,
        "diversity_weight": 0.05,
    },
    "broad": {
        "hybrid_weight": 0.5,
        "credibility_weight": 0.15,
        "diversity_weight": 0.35,
    },
}

# ── Default configuration (reads from environment, falls back to sensible defaults) ─

import os

# ── Model selection (OpenAI — cheapest model for each task) ──────────────────
#
# Task              Model                    Cost (per 1M tokens)    Why
# ─────────────────────────────────────────────────────────────────────────────
# Embeddings        text-embedding-3-small   $0.02                  Cheapest embedding
# Classification    gpt-4o-mini              $0.15 in / $0.60 out   Just yes/no decisions
# General answers   gpt-4o-mini              $0.15 in / $0.60 out   Good enough for summaries
# Math/calculation  o4-mini                  $1.10 in / $4.40 out   Best reasoning, shows work
# Image description gpt-4o-mini              $0.15 in / $0.60 out   Vision capable, cheap
#
_ENV_EMBEDDING_MODEL = os.environ.get("MAIA_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
_ENV_ANSWER_MODEL = os.environ.get("MAIA_RAG_ANSWER_MODEL", "gpt-4o-mini")
_ENV_MATH_MODEL = os.environ.get("MAIA_RAG_MATH_MODEL", "o4-mini")
_ENV_VISION_MODEL = os.environ.get("MAIA_RAG_VISION_MODEL", "gpt-4o-mini")
_ENV_CLASSIFY_MODEL = os.environ.get("MAIA_RAG_CLASSIFY_MODEL", "gpt-4o-mini")
_ENV_LLM_BASE_URL = os.environ.get("MAIA_RAG_LLM_BASE_URL", "https://api.openai.com/v1")
_ENV_EMBEDDING_BASE_URL = os.environ.get("MAIA_RAG_EMBEDDING_BASE_URL", "https://api.openai.com/v1")

DEFAULT_CONFIG = RAGConfig(
    embedding_model=_ENV_EMBEDDING_MODEL,
    embedding_dimensions=int(os.environ.get("MAIA_RAG_EMBEDDING_DIMENSIONS", "0")),
    chunk_size=int(os.environ.get("MAIA_RAG_CHUNK_SIZE", "0")),
    chunk_overlap=int(os.environ.get("MAIA_RAG_CHUNK_OVERLAP", "0")),
    preserve_formulas=True,
    preserve_tables=True,
    top_k=int(os.environ.get("MAIA_RAG_TOP_K", "20")),
    final_k=int(os.environ.get("MAIA_RAG_FINAL_K", "8")),
    hybrid_weight=float(os.environ.get("MAIA_RAG_HYBRID_WEIGHT", "0.7")),
    rerank_model=os.environ.get("MAIA_RAG_RERANK_MODEL", ""),
    credibility_weight=float(os.environ.get("MAIA_RAG_CREDIBILITY_WEIGHT", "0.2")),
    diversity_weight=float(os.environ.get("MAIA_RAG_DIVERSITY_WEIGHT", "0.1")),
    answer_model=_ENV_ANSWER_MODEL,
    math_model=_ENV_MATH_MODEL,
    vision_model=_ENV_VISION_MODEL,
    classify_model=_ENV_CLASSIFY_MODEL,
    max_answer_tokens=int(os.environ.get("MAIA_RAG_MAX_ANSWER_TOKENS", "0")),
    allow_calculations=True,
    grounding_mode=os.environ.get("MAIA_RAG_GROUNDING_MODE", "strict"),
    citation_mode=os.environ.get("MAIA_RAG_CITATION_MODE", "inline"),
    highlight_enabled=True,
    fallback_to_page=True,
    trace_enabled=True,
)


def get_config(overrides: dict | None = None) -> RAGConfig:
    """Return a RAGConfig with defaults, optionally overridden.

    Parameters
    ----------
    overrides : dict of field_name → value to override. Unknown keys are
                silently ignored. A special key "preset" can be set to one of
                the WEIGHT_PRESETS names ("balanced", "precision", "broad")
                to apply a weight preset before other overrides.

    Returns
    -------
    A fresh RAGConfig instance.
    """
    # Start from defaults by copying all fields
    config = RAGConfig(
        embedding_model=DEFAULT_CONFIG.embedding_model,
        embedding_dimensions=DEFAULT_CONFIG.embedding_dimensions,
        chunk_size=DEFAULT_CONFIG.chunk_size,
        chunk_overlap=DEFAULT_CONFIG.chunk_overlap,
        preserve_formulas=DEFAULT_CONFIG.preserve_formulas,
        preserve_tables=DEFAULT_CONFIG.preserve_tables,
        top_k=DEFAULT_CONFIG.top_k,
        final_k=DEFAULT_CONFIG.final_k,
        hybrid_weight=DEFAULT_CONFIG.hybrid_weight,
        rerank_model=DEFAULT_CONFIG.rerank_model,
        credibility_weight=DEFAULT_CONFIG.credibility_weight,
        diversity_weight=DEFAULT_CONFIG.diversity_weight,
        answer_model=DEFAULT_CONFIG.answer_model,
        max_answer_tokens=DEFAULT_CONFIG.max_answer_tokens,
        allow_calculations=DEFAULT_CONFIG.allow_calculations,
        grounding_mode=DEFAULT_CONFIG.grounding_mode,
        citation_mode=DEFAULT_CONFIG.citation_mode,
        highlight_enabled=DEFAULT_CONFIG.highlight_enabled,
        fallback_to_page=DEFAULT_CONFIG.fallback_to_page,
        trace_enabled=DEFAULT_CONFIG.trace_enabled,
    )

    if not overrides:
        return config

    # Apply weight preset first if specified
    preset_name = overrides.pop("preset", None) if isinstance(overrides, dict) else None
    if preset_name and preset_name in WEIGHT_PRESETS:
        for key, value in WEIGHT_PRESETS[preset_name].items():
            if hasattr(config, key):
                setattr(config, key, value)

    # Apply individual overrides
    for key, value in overrides.items():
        if hasattr(config, key):
            setattr(config, key, value)

    return config


def classify_credibility(source_url: str) -> str:
    """Classify a URL or filename into a credibility tier.

    Returns "high", "medium", "low", or "unknown".
    """
    url_lower = source_url.lower()
    for domain in CREDIBILITY_HIGH:
        if domain in url_lower:
            return "high"
    for domain in CREDIBILITY_MEDIUM:
        if domain in url_lower:
            return "medium"
    for domain in CREDIBILITY_LOW:
        if domain in url_lower:
            return "low"
    return "unknown"
