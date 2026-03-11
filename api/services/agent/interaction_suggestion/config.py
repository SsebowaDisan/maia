from __future__ import annotations

import os

from api.services.agent.llm_runtime import env_bool

# Master switch.  Off by default — enable with MAIA_LLM_INTERACTION_SUGGESTIONS_ENABLED=true.
LLM_INTERACTION_SUGGESTIONS_ENABLED: bool = env_bool(
    "MAIA_LLM_INTERACTION_SUGGESTIONS_ENABLED",
    default=False,
)

# Suggestions whose confidence falls below this threshold are silently dropped.
LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE: float = max(
    0.0,
    min(
        1.0,
        float(
            os.getenv("MAIA_LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE", "0.4") or "0.4"
        ),
    ),
)

# Hard cap on how many suggestion events may fire per step invocation.
LLM_INTERACTION_SUGGESTION_MAX_PER_STEP: int = max(
    0,
    int(os.getenv("MAIA_LLM_INTERACTION_SUGGESTION_MAX_PER_STEP", "5") or "5"),
)
