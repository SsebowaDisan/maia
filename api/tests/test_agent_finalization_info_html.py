from api.services.agent.models import AgentSource
from api.services.agent.orchestration.finalization import (
    _build_evidence_items_from_sources,
    _build_info_html_from_sources,
    _extract_citation_url_to_idx,
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
                "confidence": 0.84,
                "agent_role": "research",
                "graph_node_id": "node-14",
                "scene_ref": "scene.browser.main",
                "event_id": "evt-411",
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
    assert "data-confidence='0.840000'" in info_html
    assert "data-collected-by='research'" in info_html
    assert "data-source-type='web'" in info_html
    assert "data-graph-node-id='node-14'" in info_html
    assert "data-scene-ref='scene.browser.main'" in info_html
    assert "data-event-ref='evt-411'" in info_html
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


def test_build_evidence_items_from_sources_emits_info_panel_payload() -> None:
    sources = [
        AgentSource(
            source_type="file",
            label="Quarterly report",
            file_id="file-77",
            score=0.62,
            metadata={
                "page_label": "12",
                "excerpt": "Revenue increased by 14% year over year.",
                "graph_node_ids": ["node-a", "node-b"],
                "scene_refs": ["scene.pdf.reader"],
                "event_refs": ["evt-1", "evt-2"],
                "highlight_boxes": [{"x": 0.05, "y": 0.1, "width": 0.4, "height": 0.07}],
            },
        )
    ]

    rows = _build_evidence_items_from_sources(sources)
    assert len(rows) == 1

    payload = rows[0].to_info_panel_payload()
    assert payload["id"] == "evidence-1"
    assert payload["source_type"] == "file"
    assert payload["file_id"] == "file-77"
    assert payload["page"] == "12"
    assert payload["extract"].startswith("Revenue increased")
    assert payload["graph_node_ids"] == ["node-a", "node-b"]
    assert payload["scene_refs"] == ["scene.pdf.reader"]
    assert payload["event_refs"] == ["evt-1", "evt-2"]
    assert payload.get("region", {}).get("x") == 0.05


def test_extract_citation_url_to_idx_parses_evidence_citations_section() -> None:
    answer = (
        "## Executive Summary\n"
        "Key finding about machine learning.\n\n"
        "## Evidence Citations\n"
        "- [1] [Harvard SEAS](https://seas.harvard.edu/news/article)\n"
        "- [2] [Virginia DS](https://datascience.virginia.edu/report)\n"
        "- [3] Internal evidence | internal evidence\n"
    )
    mapping = _extract_citation_url_to_idx(answer)
    assert mapping.get("https://seas.harvard.edu/news/article") == 1
    assert mapping.get("https://datascience.virginia.edu/report") == 2
    # Internal (non-URL) entries must not appear
    assert len(mapping) == 2


def test_citation_url_to_idx_missing_section_returns_empty() -> None:
    assert _extract_citation_url_to_idx("No citation section here.") == {}


def test_evidence_ids_align_with_citation_list_when_sources_include_non_url_entries() -> None:
    """Regression: before fix, source #95 (first URL source) got evidence-95
    in info_html but [1] in the citation list, breaking anchor → panel linking."""
    # Build 3 sources: first is file-only (no URL), second and third are web URLs.
    sources = [
        AgentSource(source_type="file", label="Internal report", file_id="f-1"),
        AgentSource(source_type="web", label="Harvard", url="https://seas.harvard.edu/news/ml"),
        AgentSource(source_type="web", label="Virginia DS", url="https://datascience.virginia.edu/ai"),
    ]
    citation_url_to_idx = {
        "https://seas.harvard.edu/news/ml": 1,
        "https://datascience.virginia.edu/ai": 2,
    }
    items = _build_evidence_items_from_sources(sources, citation_url_to_idx=citation_url_to_idx)
    id_map = {item.source_url: item.evidence_id for item in items}

    # The URL sources must use the citation list index, not their sequential position.
    assert id_map.get("https://seas.harvard.edu/news/ml") == "evidence-1"
    assert id_map.get("https://datascience.virginia.edu/ai") == "evidence-2"
    # The non-URL source gets the first sequential ID that doesn't collide with
    # the claimed citation IDs {1, 2}, which is 3.
    non_url_item = next(i for i in items if not i.source_url)
    assert non_url_item.evidence_id == "evidence-3"


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
