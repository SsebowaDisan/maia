"""Model pricing helpers.

Single responsibility:
resolve token pricing with local/open-source awareness.
"""
from __future__ import annotations

from typing import Any

from api.services.computer_use.runtime_config import is_open_source_model, normalize_model_name

PRICING_PER_M: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {"in": 15.0, "out": 75.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-haiku-4-5": {"in": 0.8, "out": 4.0},
}
DEFAULT_PRICING_PER_M = {"in": 3.0, "out": 15.0}


def resolve_pricing_per_m(model: str | None) -> dict[str, float]:
    """Return per-million-token pricing for a model.

    Local/open-source models default to 0 token cost in Maia metering so
    tenant budgets are not inflated by hosted-provider estimates.
    """
    if _is_local_or_open_source(model):
        return {"in": 0.0, "out": 0.0}
    normalized = normalize_model_name(model or "")
    return PRICING_PER_M.get(normalized, DEFAULT_PRICING_PER_M)


def _is_local_or_open_source(model: str | None) -> bool:
    raw = str(model or "").strip()
    if not raw:
        return False
    if raw.lower().startswith("ollama::"):
        return True
    return is_open_source_model(raw)


def calculate_token_cost_usd(*, model: str | None, tokens_in: int, tokens_out: int) -> float:
    pricing = resolve_pricing_per_m(model)
    return (tokens_in / 1_000_000 * pricing["in"]) + (tokens_out / 1_000_000 * pricing["out"])


def pricing_summary(model: str | None) -> dict[str, Any]:
    pricing = resolve_pricing_per_m(model)
    return {
        "model": normalize_model_name(model or ""),
        "tokens_in_per_m_usd": pricing["in"],
        "tokens_out_per_m_usd": pricing["out"],
    }
