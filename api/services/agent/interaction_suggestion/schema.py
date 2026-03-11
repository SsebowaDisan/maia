from __future__ import annotations

import dataclasses
from typing import Any

# Exhaustive set of allowed interaction actions.  Any LLM output outside this
# set is rejected so we can never route an unknown action into execution logic.
VALID_ACTIONS: frozenset[str] = frozenset(
    {"navigate", "click", "hover", "type", "scroll", "extract", "verify", "highlight", "search"}
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclasses.dataclass(frozen=True)
class InteractionSuggestionPayload:
    """Validated, immutable representation of one LLM-generated interaction hint.

    ``advisory`` is always ``True`` — this payload is a UI hint only and must
    never be fed into execution or automation logic.
    """

    action: str          # one of VALID_ACTIONS
    target_label: str    # human-readable surface label, max 200 chars
    cursor_x: float      # 0–100, percent horizontal position
    cursor_y: float      # 0–100, percent vertical position
    scroll_percent: float  # 0–100, how far to scroll (0 for non-scroll actions)
    confidence: float    # 0–1, model-assigned confidence
    reason: str          # one-sentence rationale, max 280 chars
    highlight_text: str = ""  # exact text to highlight or search term (empty if not applicable)
    advisory: bool = dataclasses.field(default=True, init=False)  # always True

    def __post_init__(self) -> None:
        # Enforce advisory invariant even if someone tries to build the object
        # programmatically.  frozen=True means we use object.__setattr__.
        object.__setattr__(self, "advisory", True)


def validate_and_clamp(raw: dict[str, Any]) -> InteractionSuggestionPayload | None:
    """Parse *raw* LLM output into a validated payload, or return ``None``.

    Clamping rules
    --------------
    * ``cursor_x / cursor_y`` → clamped to [0, 100]
    * ``scroll_percent``      → clamped to [0, 100]
    * ``confidence``          → clamped to [0, 1]
    * ``action``              → must be in VALID_ACTIONS, else rejected
    * ``target_label``        → truncated to 200 chars
    * ``reason``              → truncated to 280 chars
    * ``highlight_text``      → truncated to 200 chars
    """
    if not isinstance(raw, dict):
        return None
    try:
        action = str(raw.get("action") or "").strip().lower()
        if action not in VALID_ACTIONS:
            return None

        target_label = str(raw.get("target_label") or "").strip()[:200]
        cursor_x = round(_clamp(float(raw.get("cursor_x") or 50.0), 0.0, 100.0), 2)
        cursor_y = round(_clamp(float(raw.get("cursor_y") or 50.0), 0.0, 100.0), 2)
        scroll_percent = round(
            _clamp(float(raw.get("scroll_percent") or 0.0), 0.0, 100.0), 2
        )
        confidence = round(_clamp(float(raw.get("confidence") or 0.0), 0.0, 1.0), 3)
        reason = str(raw.get("reason") or "").strip()[:280]
        highlight_text = str(raw.get("highlight_text") or "").strip()[:200]

        return InteractionSuggestionPayload(
            action=action,
            target_label=target_label,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            scroll_percent=scroll_percent,
            confidence=confidence,
            reason=reason,
            highlight_text=highlight_text,
        )
    except Exception:
        return None


def payload_to_metadata(suggestion: InteractionSuggestionPayload) -> dict[str, Any]:
    """Serialise *suggestion* to a flat metadata dict suitable for event emission.

    The ``__no_execution`` and ``advisory`` guards are always injected here so
    downstream consumers cannot accidentally interpret this as a live action.
    """
    return {
        "action": suggestion.action,
        "target_label": suggestion.target_label,
        "cursor_x": suggestion.cursor_x,
        "cursor_y": suggestion.cursor_y,
        "scroll_percent": suggestion.scroll_percent,
        "confidence": suggestion.confidence,
        "reason": suggestion.reason,
        "highlight_text": suggestion.highlight_text,
        "advisory": True,
        "__no_execution": True,
    }
