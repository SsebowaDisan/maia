from __future__ import annotations

from api.services.agent.reasoning.evolution_store import EvolutionStore


def test_prompt_overlay_does_not_fall_back_to_unrelated_lessons(tmp_path) -> None:
    store = EvolutionStore(tenant_id="tenant-1", base_dir=str(tmp_path))
    store.record_lesson(
        lesson="Agent 'Email Editor' not found while sending a workflow email.",
        category="writing",
        source_run_id="run-1",
    )
    store.record_lesson(
        lesson="Search results need stronger source deduplication before synthesis.",
        category="research",
        source_run_id="run-2",
    )

    overlay = store.get_prompt_overlay(stage="mystery-specialist", max_lessons=5)

    assert overlay == ""


def test_prompt_overlay_scopes_specialist_stage_to_matching_category(tmp_path) -> None:
    store = EvolutionStore(tenant_id="tenant-2", base_dir=str(tmp_path))
    store.record_lesson(
        lesson="Use concise executive structure with citations in outbound email drafts.",
        category="writing",
        source_run_id="run-1",
    )
    store.record_lesson(
        lesson="Search broad sources before narrowing into benchmark comparisons.",
        category="research",
        source_run_id="run-2",
    )

    overlay = store.get_prompt_overlay(stage="email-specialist", max_lessons=5)

    assert "outbound email drafts" in overlay
    assert "benchmark comparisons" not in overlay
