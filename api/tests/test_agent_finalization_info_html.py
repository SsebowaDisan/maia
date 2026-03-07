from api.services.agent.models import AgentSource
from api.services.agent.orchestration.finalization import (
    _build_info_html_from_sources,
    _post_resume_verification_state,
)


def test_build_info_html_from_sources_emits_structured_evidence_blocks() -> None:
    sources = [
        AgentSource(
            source_type="web",
            label="Axon Group | About",
            url="https://axongroup.com/about-axon",
            metadata={
                "page_label": "3",
                "extract": "Axon Group is family-owned and led by the second generation.",
                "match_quality": "exact",
                "unit_id": "u-123",
                "char_start": 10,
                "char_end": 92,
                "strength_score": 0.73125,
                "highlight_boxes": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.04}],
            },
        ),
        AgentSource(
            source_type="file",
            label="Internal PDF",
            file_id="file-2",
            metadata={
                "page_label": "7",
                "excerpt": "Operational notes from the internal audit.",
            },
        ),
    ]

    info_html = _build_info_html_from_sources(sources)

    assert "data-layout='kotaemon'" in info_html
    assert "<details class='evidence' id='evidence-1'" in info_html
    assert "data-evidence-id='evidence-1'" in info_html
    assert "data-source-url='https://axongroup.com/about-axon'" in info_html
    assert "data-file-id='file-2'" in info_html
    assert "data-strength='0.731250'" in info_html
    assert "data-strength-tier='3'" in info_html
    assert "data-boxes='[{&quot;x&quot;:0.1,&quot;y&quot;:0.2,&quot;width&quot;:0.3,&quot;height&quot;:0.04}]'" in info_html
    assert info_html.count(" open>") == 1


def test_build_info_html_from_sources_sanitizes_noisy_web_labels_and_artifact_urls() -> None:
    sources = [
        AgentSource(
            source_type="web",
            label="/axongroup.com/ Published Time: Wed, 04 Mar 2026 17:48:40 GMT Markdown Content: Axon Group | Industrial solutions",
            url="https://example.com/url",
            metadata={},
        )
    ]

    info_html = _build_info_html_from_sources(sources)

    assert "Published Time" not in info_html
    assert "Markdown Content" not in info_html
    assert "data-source-url=" not in info_html
    assert "<b>Extract:</b>" not in info_html


def test_post_resume_verification_state_clears_pending_barrier_when_contract_is_ready() -> None:
    settings: dict[str, object] = {"__barrier_resume_pending_verification": True}
    state = _post_resume_verification_state(
        settings=settings,  # type: ignore[arg-type]
        contract_check_result={"ready_for_external_actions": True},
        final_missing_items=[],
        handoff_state={"state": "resumed"},
    )
    assert state["blocked"] is False
    assert state["cleared"] is True
    assert settings.get("__barrier_resume_pending_verification") is False
    assert settings.get("__barrier_resume_verified_at")


def test_post_resume_verification_state_blocks_when_contract_missing_items_remain() -> None:
    settings: dict[str, object] = {"__barrier_resume_pending_verification": True}
    state = _post_resume_verification_state(
        settings=settings,  # type: ignore[arg-type]
        contract_check_result={"ready_for_external_actions": False},
        final_missing_items=["Missing confirmation"],
        handoff_state={"state": "resumed"},
    )
    assert state["blocked"] is True
    assert state["cleared"] is False
    assert settings.get("__barrier_resume_pending_verification") is True
    assert "Post-resume verification" in str(settings.get("__barrier_resume_verification_note") or "")
