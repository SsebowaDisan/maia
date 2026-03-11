from __future__ import annotations

import logging

from decouple import config

DEFAULT_SETTING = "(default)"
logger = logging.getLogger(__name__)
PLACEHOLDER_KEYS = {
    "",
    "your-key",
    "<your_openai_key>",
    "changeme",
    "none",
    "null",
}
API_CHAT_FAST_PATH = config("MAIA_API_CHAT_FAST_PATH", default=True, cast=bool)
API_FAST_QA_MAX_IMAGES = config("MAIA_FAST_QA_MAX_IMAGES", default=4, cast=int)
API_FAST_QA_MAX_SNIPPETS = config("MAIA_FAST_QA_MAX_SNIPPETS", default=30, cast=int)
API_FAST_QA_SOURCE_SCAN = config("MAIA_FAST_QA_SOURCE_SCAN", default=220, cast=int)
API_FAST_QA_MAX_SOURCES = config("MAIA_FAST_QA_MAX_SOURCES", default=35, cast=int)
API_FAST_QA_MAX_CHUNKS_PER_SOURCE = config(
    "MAIA_FAST_QA_MAX_CHUNKS_PER_SOURCE",
    default=6,
    cast=int,
)
API_FAST_QA_TEMPERATURE = config("MAIA_FAST_QA_TEMPERATURE", default=0.35, cast=float)
MAIA_CITATION_STRENGTH_ORDERING_ENABLED = config(
    "MAIA_CITATION_STRENGTH_ORDERING_ENABLED",
    default=False,
    cast=bool,
)
MAIA_CITATION_ANCHOR_INDEX_ENABLED = config(
    "MAIA_CITATION_ANCHOR_INDEX_ENABLED",
    default=True,
    cast=bool,
)
MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED = config(
    "MAIA_CITATION_RICH_ANCHOR_METADATA_ENABLED",
    default=False,
    cast=bool,
)
MAIA_CITATION_FUZZY_MATCH_ENABLED = config(
    "MAIA_CITATION_FUZZY_MATCH_ENABLED",
    default=True,
    cast=bool,
)
MAIA_CITATION_UNIFIED_REFS_ENABLED = config(
    "MAIA_CITATION_UNIFIED_REFS_ENABLED",
    default=True,
    cast=bool,
)
MAIA_CITATION_STRENGTH_BADGES_ENABLED = config(
    "MAIA_CITATION_STRENGTH_BADGES_ENABLED",
    default=True,
    cast=bool,
)
MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED = config(
    "MAIA_CITATION_CONTRADICTION_SIGNALS_ENABLED",
    default=True,
    cast=bool,
)
MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL = config(
    "MAIA_CITATION_STRENGTH_WEIGHT_RETRIEVAL",
    default=0.5,
    cast=float,
)
MAIA_CITATION_STRENGTH_WEIGHT_LLM = config(
    "MAIA_CITATION_STRENGTH_WEIGHT_LLM",
    default=0.4,
    cast=float,
)
MAIA_CITATION_STRENGTH_WEIGHT_SPAN = config(
    "MAIA_CITATION_STRENGTH_WEIGHT_SPAN",
    default=0.1,
    cast=float,
)
MAIA_SOURCE_USAGE_HEATMAP_ENABLED = config(
    "MAIA_SOURCE_USAGE_HEATMAP_ENABLED",
    default=False,
    cast=bool,
)
MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD = config(
    "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD",
    default=0.60,
    cast=float,
)
# Source federation feature flags (S1)
MAIA_ARXIV_ENABLED = config("MAIA_ARXIV_ENABLED", default=False, cast=bool)
MAIA_SEC_EDGAR_ENABLED = config("MAIA_SEC_EDGAR_ENABLED", default=False, cast=bool)
MAIA_NEWSAPI_ENABLED = config("MAIA_NEWSAPI_ENABLED", default=False, cast=bool)
MAIA_REDDIT_ENABLED = config("MAIA_REDDIT_ENABLED", default=False, cast=bool)
MAIA_EXPERT_MODE_ENABLED = config("MAIA_EXPERT_MODE_ENABLED", default=False, cast=bool)
MAIA_SOURCE_CREDIBILITY_ENABLED = config("MAIA_SOURCE_CREDIBILITY_ENABLED", default=True, cast=bool)
