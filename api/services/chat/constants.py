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
API_FAST_QA_MAX_IMAGES = config("MAIA_FAST_QA_MAX_IMAGES", default=2, cast=int)
API_FAST_QA_MAX_SNIPPETS = config("MAIA_FAST_QA_MAX_SNIPPETS", default=14, cast=int)
API_FAST_QA_SOURCE_SCAN = config("MAIA_FAST_QA_SOURCE_SCAN", default=120, cast=int)
API_FAST_QA_MAX_SOURCES = config("MAIA_FAST_QA_MAX_SOURCES", default=18, cast=int)
API_FAST_QA_MAX_CHUNKS_PER_SOURCE = config(
    "MAIA_FAST_QA_MAX_CHUNKS_PER_SOURCE",
    default=3,
    cast=int,
)
API_FAST_QA_TEMPERATURE = config("MAIA_FAST_QA_TEMPERATURE", default=0.2, cast=float)
MAIA_CITATION_STRENGTH_ORDERING_ENABLED = config(
    "MAIA_CITATION_STRENGTH_ORDERING_ENABLED",
    default=False,
    cast=bool,
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
