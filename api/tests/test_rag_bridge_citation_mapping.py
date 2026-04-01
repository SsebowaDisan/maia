from api.services.rag.bridge import _build_info_panel, _inject_citation_anchors


def test_inject_citation_anchor_uses_ui_page_and_evidence_id() -> None:
    html = _inject_citation_anchors(
        "Answer line [1].",
        [
            {
                "ref_id": "[1]",
                "source_id": "src_pdf_1",
                "source_type": "pdf",
                "page": 1,  # pipeline is 0-indexed -> UI should show page 2
                "snippet": "Important sentence.",
                "relevance_score": 0.8,
            }
        ],
    )

    assert 'class="citation"' in html
    assert 'data-evidence-id="evidence-1"' in html
    assert 'data-page="2"' in html
    assert 'data-file-id="src_pdf_1"' in html
    assert 'data-viewer-url="/api/uploads/files/src_pdf_1/raw"' in html


def test_inject_citation_anchor_does_not_mark_url_source_as_file_backed() -> None:
    html = _inject_citation_anchors(
        "Answer line [1].",
        [
            {
                "ref_id": "[1]",
                "source_id": "src_url_1",
                "source_type": "url",
                "url": "https://example.com/page",
                "page": 0,
                "snippet": "Web evidence.",
                "relevance_score": 0.7,
            }
        ],
    )

    assert 'data-source-url="https://example.com/page"' in html
    assert 'data-file-id="' not in html
    assert 'data-viewer-url="' not in html


def test_build_info_panel_converts_page_to_ui_number() -> None:
    panel = _build_info_panel(
        evidence_items=[
            {
                "source_id": "src_pdf_1",
                "source_name": "doc.pdf",
                "page": 2,  # 0-indexed -> page 3 in UI
                "snippet": "Evidence snippet",
                "relevance_score": 0.9,
                "heading_path": [],
                "ref_id": "[1]",
            }
        ],
        citations=[
            {
                "ref_id": "[1]",
                "source_type": "pdf",
                "relevance_score": 0.9,
            }
        ],
        sources_used=[
            {
                "source_id": "src_pdf_1",
                "source_name": "doc.pdf",
                "source_type": "pdf",
            }
        ],
        payload=None,  # not used by helper
    )

    item = panel["evidence_items"][0]
    assert item["page"] == "3"
    assert item["review_location"]["page"] == "3"
    assert item["review_location"]["surface"] == "pdf"
