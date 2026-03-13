from __future__ import annotations

import logging
from typing import Any

from api.services.agent.llm_runtime import call_json_response

from .schema import InteractionSuggestionPayload, validate_and_clamp

logger = logging.getLogger(__name__)

# Tool-id prefix → human-readable surface name fed into the prompt.
_TOOL_SURFACE_LABELS: tuple[tuple[str, str], ...] = (
    ("browser.", "web page"),
    ("web.", "web page"),
    ("marketing.web_research", "web page"),
    ("docs.", "Google Doc"),
    ("workspace.docs", "Google Doc"),
    ("sheets.", "spreadsheet"),
    ("workspace.sheets", "spreadsheet"),
    ("gmail.", "email draft"),
    ("email.", "email draft"),
    ("drive.", "Google Drive"),
)


def _tool_surface_label(tool_id: str) -> str:
    tid = str(tool_id or "").lower().strip()
    for prefix, label in _TOOL_SURFACE_LABELS:
        if tid.startswith(prefix) or tid == prefix.rstrip("."):
            return label
    return "document"


def _has_strong_deterministic_params(step_params: dict[str, Any]) -> bool:
    """Return True when the step's planned params already carry explicit coordinates
    so the LLM suggestion path can be skipped entirely."""
    has_cursor = (
        step_params.get("x") is not None and step_params.get("y") is not None
    ) or (
        step_params.get("target_x") is not None and step_params.get("target_y") is not None
    )
    has_selector = bool(
        str(step_params.get("selector") or step_params.get("target_selector") or "").strip()
    )
    return has_cursor or has_selector


def _build_plan_excerpt(step_params: dict[str, Any], max_chars: int = 400) -> str:
    """Extract a concise, LLM-readable excerpt from the planned step params."""
    keys = ["url", "query", "selector", "target", "field", "subject", "to", "value", "text"]
    parts: list[str] = []
    for key in keys:
        val = step_params.get(key)
        if val is None:
            continue
        snippet = str(val)[:120].replace("\n", " ")
        parts.append(f"{key}: {snippet}")
    return "; ".join(parts)[:max_chars]


_SUGGESTION_PROMPT_TEMPLATE = """\
You are an agent interaction coach. A browser/document automation step is about to run.
Suggest 5 focused interactions that help a human follow along on the {surface}.

Return a JSON object with EXACTLY this structure (no markdown, no extra keys):
{{
  "interactions": [
    {{
      "action": "one of: navigate, click, hover, type, scroll, extract, verify, highlight, search",
      "target_label": "short label for where to focus (max 80 chars)",
      "cursor_x": <float 0-100, horizontal percent on {surface}>,
      "cursor_y": <float 0-100, vertical percent on {surface}>,
      "scroll_percent": <float 0-100, 0 if action is not scroll>,
      "confidence": <float 0-1>,
      "reason": "one sentence why (max 80 chars)",
      "highlight_text": "exact text to highlight or search term, empty string if not applicable",
      "primary": <true for your single top recommendation, false for all others>
    }}
  ]
}}

Include a mix of:
- Navigation links or menu buttons to click (action: navigate or click)
- Specific page sections or elements to check (action: hover or verify)
- Words or phrases to search for on the page (action: search, set highlight_text to the search query)
- Exact sentences or terms to highlight during reading (action: highlight, set highlight_text)
- Scroll positions to reach important content (action: scroll)

User goal: {task_context}
Step {step_index} of {total_steps}: {step_title}
Tool: {tool_id}
Surface: {surface}
Why this step: {step_why}
Planned params: {plan_excerpt}

Rules:
- Produce exactly 5 interaction objects in the array.
- Each interaction must have a plausible cursor_x/cursor_y on the {surface}.
- Vary the action types — do not repeat the same action 5 times.
- For highlight or search actions, always populate highlight_text with the relevant text.
- Never suggest actions that send data, authenticate, or modify state.
- For low-relevance steps, lower confidence values (0.3–0.5) are fine.
- Rank your suggestions from most to least recommended. Set primary=true on EXACTLY ONE item (the best one). All others must have primary=false.
"""


def generate_interaction_suggestion(
    *,
    tool_id: str,
    step_title: str,
    step_why: str,
    step_params: dict[str, Any],
    task_context: str,
    step_index: int,
    total_steps: int,
) -> list[InteractionSuggestionPayload]:
    """Call the LLM to generate pre-execution interaction suggestions (up to 5).

    Called before the step runs so hints reach the UI while execution is in
    progress, not after it completes.

    Returns an empty list when:
    - the step params already carry explicit coordinates/selector (deterministic skip)
    - the LLM call fails
    - the response fails schema validation
    """
    if _has_strong_deterministic_params(step_params):
        logger.debug(
            "interaction_suggestion.skipped_deterministic: tool_id=%s", tool_id
        )
        return []

    surface = _tool_surface_label(tool_id)
    plan_excerpt = _build_plan_excerpt(step_params)

    prompt = _SUGGESTION_PROMPT_TEMPLATE.format(
        tool_id=str(tool_id or "")[:80],
        step_title=str(step_title or "")[:140],
        surface=surface,
        step_why=str(step_why or "")[:200],
        plan_excerpt=plan_excerpt,
        task_context=str(task_context or "")[:120],
        step_index=step_index,
        total_steps=total_steps,
    )

    try:
        raw = call_json_response(
            prompt=prompt,
            system=(
                "You output JSON only. No prose, no markdown fences, no extra keys. "
                'Return a JSON object with an "interactions" array of exactly 5 items.'
            ),
        )
        if not isinstance(raw, dict):
            logger.debug(
                "interaction_suggestion.invalid_response: tool_id=%s raw=%s",
                tool_id,
                str(raw)[:120],
            )
            return []

        raw_list = raw.get("interactions")
        if not isinstance(raw_list, list):
            logger.debug(
                "interaction_suggestion.missing_interactions_key: tool_id=%s raw=%s",
                tool_id,
                str(raw)[:120],
            )
            return []

        suggestions: list[InteractionSuggestionPayload] = []
        for item in raw_list:
            payload = validate_and_clamp(item)
            if payload is not None:
                suggestions.append(payload)

        # Enforce primary invariant: exactly one suggestion must be primary=True.
        # If the LLM marked zero or multiple, programmatically assign the
        # highest-confidence one and clear the rest.
        primary_count = sum(1 for s in suggestions if s.primary)
        if primary_count != 1 and suggestions:
            import dataclasses as _dc
            best_idx = max(range(len(suggestions)), key=lambda i: suggestions[i].confidence)
            fixed: list[InteractionSuggestionPayload] = []
            for idx, s in enumerate(suggestions):
                if s.primary != (idx == best_idx):
                    s = _dc.replace(s, primary=(idx == best_idx))
                fixed.append(s)
            suggestions = fixed

        return suggestions
    except Exception as exc:
        logger.debug("interaction_suggestion.llm_error: tool_id=%s error=%s", tool_id, exc)
        return []
