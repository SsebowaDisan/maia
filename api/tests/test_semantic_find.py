from __future__ import annotations

from api.services.agent.execution.semantic_find import apply_semantic_find


def test_apply_semantic_find_derives_ranked_results_from_query_variants() -> None:
    payload = apply_semantic_find(
        event_type="retrieval_query_rewrite",
        data={
            "query_variants": [
                "axon group industrial solutions",
                "axon group fluids air powder",
                "axon group control heat exchange",
            ]
        },
    )
    results = list(payload.get("semantic_find_results") or [])
    assert payload.get("semantic_find_source") == "query_variants"
    assert payload.get("semantic_find_query")
    assert payload.get("semantic_find_terms")[:2] == [
        "axon group industrial solutions",
        "axon group fluids air powder",
    ]
    assert len(results) == 3
    assert results[0]["rank"] == 1
    assert results[0]["confidence"] >= results[1]["confidence"] >= results[2]["confidence"]


def test_apply_semantic_find_preserves_explicit_semantic_results() -> None:
    payload = apply_semantic_find(
        event_type="browser_find_in_page",
        data={
            "find_query": "operating margin",
            "semantic_find_results": [
                {"term": "operating margin", "confidence": 0.92, "rank": 1},
                {"term": "gross margin", "score": 0.78, "rank": 2},
            ],
        },
    )
    results = payload.get("semantic_find_results") or []
    assert len(results) == 2
    assert results[0]["term"] == "operating margin"
    assert results[0]["confidence"] == 0.92
    assert results[1]["term"] == "gross margin"
    assert 0.0 <= results[1]["confidence"] <= 1.0
