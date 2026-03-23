from __future__ import annotations

from api.services.agent.orchestration.step_execution_sections import success


def test_standard_research_does_not_insert_live_source_followups_by_branching_mode() -> None:
    assert not success._should_insert_live_source_followups(
        settings={
            "__research_depth_tier": "standard",
            "__research_branching_mode": "segmented",
        },
        deep_research_mode=False,
    )


def test_deep_research_still_allows_live_source_followups() -> None:
    assert success._should_insert_live_source_followups(
        settings={"__research_depth_tier": "deep_research"},
        deep_research_mode=False,
    )


def test_target_url_keeps_live_source_followups_enabled() -> None:
    assert success._should_insert_live_source_followups(
        settings={
            "__research_depth_tier": "standard",
            "__task_target_url": "https://example.com/report",
        },
        deep_research_mode=False,
    )
