from __future__ import annotations

from api.services.observability.model_pricing import (
    calculate_token_cost_usd,
    resolve_pricing_per_m,
)


def test_resolve_pricing_per_m_for_hosted_model() -> None:
    pricing = resolve_pricing_per_m("claude-sonnet-4-6")
    assert pricing == {"in": 3.0, "out": 15.0}


def test_resolve_pricing_per_m_for_open_source_model_is_zero() -> None:
    pricing = resolve_pricing_per_m("qwen2.5vl:7b")
    assert pricing == {"in": 0.0, "out": 0.0}


def test_resolve_pricing_per_m_for_ollama_prefixed_model_is_zero() -> None:
    pricing = resolve_pricing_per_m("ollama::llama3.2:3b")
    assert pricing == {"in": 0.0, "out": 0.0}


def test_calculate_token_cost_usd_zero_for_local_model() -> None:
    cost = calculate_token_cost_usd(
        model="qwen2.5vl:7b",
        tokens_in=500_000,
        tokens_out=250_000,
    )
    assert cost == 0.0
