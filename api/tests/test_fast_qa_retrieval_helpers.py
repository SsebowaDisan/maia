from api.services.chat.fast_qa_retrieval_helpers import _ranked_chunk_selection
from api.services.chat.fast_qa_source_helpers import prioritize_primary_evidence


def test_ranked_chunk_selection_prefers_page_diversity_within_one_source() -> None:
    rows = [
        {"source_key": "file-1", "page_label": "69", "score": 15, "text": "page 69 chunk a"},
        {"source_key": "file-1", "page_label": "69", "score": 14, "text": "page 69 chunk b"},
        {"source_key": "file-1", "page_label": "66", "score": 13, "text": "page 66 chunk a"},
        {"source_key": "file-1", "page_label": "8", "score": 12, "text": "page 8 chunk a"},
    ]

    selected = _ranked_chunk_selection(rows, chunk_limit=3)

    assert len(selected) == 3
    assert [str(item.get("page_label")) for item in selected] == ["69", "66", "8"]


def test_prioritize_primary_evidence_prefers_page_diversity_within_one_primary_source() -> None:
    rows = [
        {"source_name": "Doc.pdf", "source_id": "file-1", "page_label": "69", "score": 15, "text": "page 69 a", "is_primary_source": True},
        {"source_name": "Doc.pdf", "source_id": "file-1", "page_label": "69", "score": 14, "text": "page 69 b", "is_primary_source": True},
        {"source_name": "Doc.pdf", "source_id": "file-1", "page_label": "66", "score": 13, "text": "page 66 a", "is_primary_source": True},
        {"source_name": "Doc.pdf", "source_id": "file-1", "page_label": "8", "score": 12, "text": "page 8 a", "is_primary_source": True},
    ]

    selected = prioritize_primary_evidence(
        rows,
        max_keep=3,
        max_secondary=0,
        snippet_score_fn=lambda row: int(row.get("score", 0) or 0),
    )

    assert len(selected) == 3
    assert [str(item.get("page_label")) for item in selected] == ["69", "66", "8"]
