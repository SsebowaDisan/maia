from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR / "libs" / "maia"))

from maia.mindmap.indexer import (
    build_knowledge_map,
    compute_balanced_tree_layout,
    parse_pdf_structure,
)


def test_parse_pdf_structure_returns_tree_json(monkeypatch) -> None:
    def fake_parse_pdf_to_tree(*_args, **_kwargs):
        return {
            "root_id": "root",
            "nodes": [
                {"id": "root", "title": "Document", "node_type": "root"},
                {"id": "sec_1", "title": "Section 1", "node_type": "section", "page_ref": "1"},
            ],
            "edges": [
                {
                    "id": "root->sec_1",
                    "source": "root",
                    "target": "sec_1",
                    "type": "hierarchy",
                }
            ],
        }

    monkeypatch.setattr(
        "maia.mindmap.indexer.parse_pdf_to_tree",
        fake_parse_pdf_to_tree,
    )

    payload = parse_pdf_structure("dummy.pdf", max_depth=3)

    assert payload["map_type"] == "structure"
    assert isinstance(payload.get("tree"), dict)
    assert payload["tree"]["id"] == "root"
    assert payload["tree"]["children"][0]["id"] == "sec_1"


def test_build_knowledge_map_structure_has_tree_and_cross_links() -> None:
    documents = [
        {
            "text": "Quarterly revenue growth improved cloud margins and enterprise retention.",
            "metadata": {
                "source_id": "src_a",
                "source_name": "Finance Deck A.pdf",
                "page_label": "1",
            },
        },
        {
            "text": "Enterprise retention and cloud margins improved during quarterly growth.",
            "metadata": {
                "source_id": "src_b",
                "source_name": "Finance Deck B.pdf",
                "page_label": "1",
            },
        },
    ]

    payload = build_knowledge_map(
        question="What changed in quarterly performance?",
        context="",
        documents=documents,
        include_reasoning_map=False,
        map_type="structure",
    )

    assert payload["map_type"] == "structure"
    assert isinstance(payload.get("tree"), dict) and payload["tree"].get("id") == payload.get("root_id")
    reference_edges = [
        edge for edge in payload.get("edges", []) if str(edge.get("type", "")) == "reference"
    ]
    assert reference_edges, "Expected semantic cross-source links in structure map."


def test_build_knowledge_map_evidence_has_claim_and_support_edges() -> None:
    documents = [
        {
            "text": "Operating margin expanded after automation and procurement savings.",
            "metadata": {
                "source_id": "src_a",
                "source_name": "Operations report.pdf",
                "page_label": "2",
                "score": 0.73,
            },
        },
        {
            "text": "Procurement savings improved operating margin by streamlining vendor contracts.",
            "metadata": {
                "source_id": "src_b",
                "source_name": "Finance memo.pdf",
                "page_label": "4",
                "score": 0.61,
            },
        },
    ]

    payload = build_knowledge_map(
        question="Why did margin improve?",
        context="",
        documents=documents,
        answer_text="Operating margin improved because procurement savings reduced costs.",
        include_reasoning_map=False,
        map_type="evidence",
    )

    assert payload["map_type"] == "evidence"
    claim_nodes = [node for node in payload.get("nodes", []) if node.get("node_type") == "claim"]
    support_edges = [edge for edge in payload.get("edges", []) if edge.get("type") == "support"]
    assert claim_nodes, "Evidence map should include claim nodes."
    assert support_edges, "Evidence map should include support edges."


def test_compute_balanced_tree_layout_alternates_root_sides() -> None:
    nodes = [
        {"id": "root"},
        {"id": "left_child"},
        {"id": "right_child"},
        {"id": "left_leaf"},
        {"id": "right_leaf"},
    ]
    edges = [
        {"source": "root", "target": "left_child", "type": "hierarchy"},
        {"source": "root", "target": "right_child", "type": "hierarchy"},
        {"source": "left_child", "target": "left_leaf", "type": "hierarchy"},
        {"source": "right_child", "target": "right_leaf", "type": "hierarchy"},
    ]
    positions = compute_balanced_tree_layout(root_id="root", nodes=nodes, edges=edges, max_depth=3)
    assert positions["root"]["x"] == 0.0
    assert positions["left_child"]["x"] < 0.0
    assert positions["right_child"]["x"] > 0.0
    assert abs(positions["left_child"]["x"]) == abs(positions["right_child"]["x"])
