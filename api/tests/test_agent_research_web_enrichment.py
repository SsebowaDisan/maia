from __future__ import annotations

from types import SimpleNamespace

from api.services.agent.models import AgentSource
from api.services.agent.tools.research_web_stream_enrichment import (
    run_enrichment_and_finalize_stage,
)


def _drain(generator):
    events = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value


def test_standard_overview_skips_supplemental_enrichment() -> None:
    context = SimpleNamespace(settings={})
    sources = [
        AgentSource(
            source_type="web",
            label="Machine Learning Overview",
            url="https://example.org/ml-overview",
            score=0.84,
            metadata={"excerpt": "Overview excerpt."},
        )
    ]
    bullets = ["- Machine Learning Overview: Overview excerpt."]
    state = {
        "ok": True,
        "used_provider": "brave_search",
        "provider_attempted": ["brave_search"],
        "provider_failures": [],
        "domain_scope_filtered_out": 0,
    }

    def _unexpected_registry():
        raise AssertionError("Supplemental provider registry should not be used for standard overview enrichment.")

    events, result = _drain(
        run_enrichment_and_finalize_stage(
            context=context,
            depth_tier="standard",
            branching_mode="overview",
            max_search_rounds=1,
            query="machine learning",
            query_variants=["machine learning overview"],
            min_unique_sources=1,
            results_per_query=8,
            requested_provider="brave_search",
            allow_provider_fallback=False,
            requested_search_budget=8,
            planned_result_budget=8,
            max_query_variants=4,
            fused_top_k=12,
            domain_scope_hosts=[],
            domain_scope_mode="off",
            trace_events=[],
            sources=sources,
            bullets=bullets,
            state=state,
            _research_branches=[
                {
                    "branch_label": "Factual",
                    "sub_question": "machine learning overview",
                    "preferred_providers": ["brave_search"],
                }
            ],
            get_connector_registry_fn=_unexpected_registry,
        )
    )

    event_types = [getattr(event, "event_type", "") for event in events]
    assert "research_branch_completed" not in event_types
    assert "api_call_started" not in event_types
    assert result.data["provider"] == "brave_search"
    assert result.data["source_count"] == 1


def test_standard_segmented_still_skips_supplemental_enrichment() -> None:
    context = SimpleNamespace(settings={})
    sources = [
        AgentSource(
            source_type="web",
            label="Machine Learning Overview",
            url="https://example.org/ml-overview",
            score=0.84,
            metadata={"excerpt": "Overview excerpt."},
        )
    ]
    bullets = ["- Machine Learning Overview: Overview excerpt."]
    state = {
        "ok": True,
        "used_provider": "brave_search",
        "provider_attempted": ["brave_search"],
        "provider_failures": [],
        "domain_scope_filtered_out": 0,
    }

    def _unexpected_registry():
        raise AssertionError("Standard segmented research should not trigger supplemental provider federation.")

    events, result = _drain(
        run_enrichment_and_finalize_stage(
            context=context,
            depth_tier="standard",
            branching_mode="segmented",
            max_search_rounds=1,
            query="machine learning",
            query_variants=["machine learning overview"],
            min_unique_sources=1,
            results_per_query=8,
            requested_provider="brave_search",
            allow_provider_fallback=False,
            requested_search_budget=8,
            planned_result_budget=8,
            max_query_variants=4,
            fused_top_k=12,
            domain_scope_hosts=[],
            domain_scope_mode="off",
            trace_events=[],
            sources=sources,
            bullets=bullets,
            state=state,
            _research_branches=[
                {
                    "branch_label": "Factual",
                    "sub_question": "machine learning overview",
                    "preferred_providers": ["brave_search"],
                }
            ],
            get_connector_registry_fn=_unexpected_registry,
        )
    )

    event_types = [getattr(event, "event_type", "") for event in events]
    assert "research_branch_completed" not in event_types
    assert "api_call_started" not in event_types
    assert result.data["provider"] == "brave_search"
    assert result.data["source_count"] == 1
