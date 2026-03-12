from api.services.chat.verification_contract import (
    VERIFICATION_CONTRACT_VERSION,
    build_web_review_content,
    build_verification_evidence_items,
    normalize_verification_evidence_items,
)


def test_normalize_verification_evidence_items_supports_nested_contract_fields() -> None:
    rows = normalize_verification_evidence_items(
        [
            {
                "id": "evidence-7",
                "source": {
                    "id": "file-9",
                    "type": "pdf",
                    "title": "Quarterly Report",
                    "file_id": "file-9",
                    "page": "12",
                },
                "citation": {
                    "id": "evidence-7",
                    "label": "[7]",
                    "quote": "Revenue increased by 14% year over year.",
                },
                "review_location": {
                    "surface": "pdf",
                    "file_id": "file-9",
                    "page": "12",
                },
                "highlight_target": {
                    "boxes": [
                        {
                            "x": 0.1,
                            "y": 0.2,
                            "width": 0.3,
                            "height": 0.1,
                        }
                    ],
                    "unit_id": "unit-7",
                    "char_start": 18,
                    "char_end": 72,
                },
                "evidence_quality": {
                    "score": 0.88,
                    "tier": 3,
                    "confidence": 0.84,
                    "match_quality": "exact",
                },
            }
        ]
    )
    assert rows and rows[0]["id"] == "evidence-7"
    assert rows[0]["source_type"] == "pdf"
    assert rows[0]["file_id"] == "file-9"
    assert rows[0]["page"] == "12"
    assert rows[0]["unit_id"] == "unit-7"
    assert rows[0]["char_start"] == 18
    assert rows[0]["char_end"] == 72
    assert rows[0]["strength_score"] == 0.88
    assert rows[0]["strength_tier"] == 3
    assert rows[0]["confidence"] == 0.84
    assert rows[0]["match_quality"] == "exact"
    assert rows[0].get("highlight_boxes")
    assert rows[0].get("review_location", {}).get("surface") == "pdf"


def test_build_verification_evidence_items_merges_snippet_and_ref_fields() -> None:
    items = build_verification_evidence_items(
        snippets_with_refs=[
            {
                "ref_id": 1,
                "source_name": "Axon Group | About",
                "source_url": "https://axongroup.com/about-axon",
                "page_label": "3",
                "text": "Axon Group is family-owned.",
                "unit_id": "u-1",
                "selector": "article p:nth-of-type(2)",
                "char_start": 12,
                "char_end": 40,
                "strength_score": 0.76,
                "highlight_boxes": [{"x": 0.2, "y": 0.2, "width": 0.4, "height": 0.1}],
            }
        ],
        refs=[
            {
                "id": 1,
                "source_url": "https://axongroup.com/about-axon",
                "match_quality": "exact",
            }
        ],
    )
    assert items and items[0]["id"] == "evidence-1"
    assert items[0]["source_type"] == "web"
    assert items[0]["source_url"] == "https://axongroup.com/about-axon"
    assert items[0]["match_quality"] == "exact"
    assert items[0]["strength_tier"] == 3
    assert items[0]["selector"] == "article p:nth-of-type(2)"
    assert items[0]["review_location"]["selector"] == "article p:nth-of-type(2)"
    assert items[0].get("citation", {}).get("label") == "[1]"
    assert VERIFICATION_CONTRACT_VERSION == "2026-03-08.v1"


def test_build_web_review_content_groups_web_sources_and_sanitizes_payload() -> None:
    payload = build_web_review_content(
        [
            {
                "id": "evidence-1",
                "source_type": "web",
                "source_name": "Axon Group",
                "source_url": "https://axongroup.com/about-axon",
                "extract": "Axon Group is family-owned and active in six industrial domains.",
            },
            {
                "id": "evidence-2",
                "source_type": "web",
                "source_name": "Axon Group",
                "source_url": "https://axongroup.com/about-axon",
                "extract": "The company has more than 50 years of experience.",
            },
            {
                "id": "evidence-3",
                "source_type": "pdf",
                "source_name": "Quarterly Report.pdf",
                "file_id": "file-3",
                "extract": "Revenue increased 14% YoY.",
            },
        ]
    )
    assert payload.get("version") == "web_review.v1"
    sources = payload.get("sources")
    assert isinstance(sources, list)
    assert len(sources) == 1
    first = sources[0]
    assert first.get("source_id") == "url:https://axongroup.com/about-axon"
    assert first.get("domain") == "axongroup.com"
    assert "family-owned" in str(first.get("readable_text") or "")
    assert "<p>" in str(first.get("readable_html") or "")
    assert first.get("evidence_ids") == ["evidence-1", "evidence-2"]


def test_build_web_review_content_ignores_placeholder_test_sources() -> None:
    payload = build_web_review_content(
        [
            {
                "id": "evidence-test",
                "source_type": "web",
                "source_name": "Example Domain",
                "source_url": "https://example.com/?maia_gap_test_media=1",
                "extract": "This should never surface in the review panel.",
            },
            {
                "id": "evidence-real",
                "source_type": "web",
                "source_name": "Axon Group",
                "source_url": "https://axongroup.com/about-axon",
                "extract": "Axon Group overview.",
            },
        ]
    )
    sources = payload.get("sources")
    assert isinstance(sources, list)
    assert len(sources) == 1
    assert sources[0].get("source_url") == "https://axongroup.com/about-axon"
