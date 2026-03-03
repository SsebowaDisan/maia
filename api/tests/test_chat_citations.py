from api.services.chat.citations import (
    assign_fast_source_refs,
    append_required_citation_suffix,
    build_source_usage,
    build_fast_info_html,
    collect_cited_ref_ids,
    enforce_required_citations,
    resolve_required_citation_mode,
)


def test_resolve_required_citation_mode_never_returns_off() -> None:
    assert resolve_required_citation_mode(None) == "inline"
    assert resolve_required_citation_mode("") == "inline"
    assert resolve_required_citation_mode("off") == "inline"
    assert resolve_required_citation_mode("inline") == "inline"
    assert resolve_required_citation_mode("footnote") == "inline"


def test_enforce_required_citations_uses_info_panel_refs() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Key finding without citation.",
        info_html=info_html,
        citation_mode="off",
    )
    assert "Key finding without citation." in answer
    assert "class='citation'" in answer
    assert "href='#evidence-1'" in answer


def test_append_required_citation_suffix_adds_internal_trace_when_refs_missing() -> None:
    answer = append_required_citation_suffix(
        answer="Answer without refs",
        info_html="",
    )
    assert "Evidence: internal execution trace" in answer


def test_enforce_required_citations_injects_inline_citation_when_only_tail_exists() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> test evidence extract</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="## Summary\nThe answer body has no citation markers.\n\n## Evidence Citations\n- [1] Source",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "The answer body has no citation markers. <a " in answer
    assert "data-file-id='file-1'" in answer
    assert "href='#evidence-1'" in answer
    assert "data-phrase='test evidence extract'" in answer


def test_append_required_citation_suffix_converts_plain_brackets_to_clickable_links() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='3' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer="Claim supported by source [1].",
        info_html=info_html,
    )
    assert "class='citation'" in answer
    assert "href='#evidence-1'" in answer
    assert "data-page='3'" in answer


def test_enforce_required_citations_augments_existing_anchor_attributes() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='4' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> exact evidence phrase</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim with prelinked citation <a class='citation' href='#evidence-1' id='citation-1'>[1]</a>.",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "data-file-id='file-1'" in answer
    assert "data-page='4'" in answer
    assert "data-phrase='exact evidence phrase'" in answer


def test_enforce_required_citations_adds_data_boxes_to_anchor() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' "
        "data-page='5' data-boxes='[{&quot;x&quot;:0.12,&quot;y&quot;:0.2,&quot;width&quot;:0.3,&quot;height&quot;:0.04}]' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> bounded evidence phrase</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim with citation marker [1].",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "class='citation'" in answer
    assert "data-boxes='[{&quot;x&quot;:0.12,&quot;y&quot;:0.2,&quot;width&quot;:0.3,&quot;height&quot;:0.04}]'" in answer


def test_enforce_required_citations_accepts_data_bboxes_from_info_panel() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' "
        "data-page='5' data-bboxes='[{&quot;x&quot;:0.22,&quot;y&quot;:0.3,&quot;width&quot;:0.21,&quot;height&quot;:0.05}]' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> bounded evidence phrase</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim with citation marker [1].",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "class='citation'" in answer
    assert "data-boxes='[{&quot;x&quot;:0.22,&quot;y&quot;:0.3,&quot;width&quot;:0.21,&quot;height&quot;:0.05}]'" in answer


def test_enforce_required_citations_converts_curly_brace_markers() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> citation evidence</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim supported by source {1}.",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "class='citation'" in answer
    assert "href='#evidence-1'" in answer
    assert "{1}" not in answer


def test_assign_fast_source_refs_assigns_distinct_refs_for_distinct_excerpts() -> None:
    snippets = [
        {
            "source_id": "file-1",
            "source_name": "Doc.pdf",
            "page_label": "2",
            "text": "chunk 1",
            "highlight_boxes": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.04}],
        },
        {
            "source_id": "file-1",
            "source_name": "Doc.pdf",
            "page_label": "2",
            "text": "chunk 2",
            "highlight_boxes": [{"x": 0.2, "y": 0.4, "width": 0.2, "height": 0.05}],
        },
    ]
    _enriched, refs = assign_fast_source_refs(snippets)
    assert len(refs) == 2
    assert refs[0].get("phrase") == "chunk 1"
    assert refs[1].get("phrase") == "chunk 2"


def test_assign_fast_source_refs_merges_duplicate_excerpt_boxes() -> None:
    snippets = [
        {
            "source_id": "file-1",
            "source_name": "Doc.pdf",
            "page_label": "2",
            "text": "same chunk",
            "highlight_boxes": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.04}],
        },
        {
            "source_id": "file-1",
            "source_name": "Doc.pdf",
            "page_label": "2",
            "text": "same   chunk",
            "highlight_boxes": [{"x": 0.2, "y": 0.4, "width": 0.2, "height": 0.05}],
        },
    ]
    _enriched, refs = assign_fast_source_refs(snippets)
    assert len(refs) == 1
    highlight_boxes = refs[0].get("highlight_boxes") or []
    assert isinstance(highlight_boxes, list)
    assert len(highlight_boxes) == 2


def test_build_fast_info_html_emits_data_boxes_attribute() -> None:
    info_html = build_fast_info_html(
        [
            {
                "ref_id": 1,
                "source_id": "file-1",
                "source_name": "Doc.pdf",
                "page_label": "2",
                "text": "Evidence text",
                "highlight_boxes": [{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.04}],
            }
        ]
    )
    assert "data-boxes='[{&quot;x&quot;:0.1,&quot;y&quot;:0.2,&quot;width&quot;:0.3,&quot;height&quot;:0.04}]'" in info_html


def test_build_fast_info_html_emits_strength_attribute_when_available() -> None:
    info_html = build_fast_info_html(
        [
            {
                "ref_id": 1,
                "source_id": "file-1",
                "source_name": "Doc.pdf",
                "page_label": "2",
                "text": "Evidence text",
                "strength_score": 0.73125,
            }
        ]
    )
    assert "data-strength='0.731250'" in info_html


def test_assign_fast_source_refs_strength_ordering_renumbers_refs() -> None:
    snippets = [
        {
            "source_id": "file-1",
            "source_name": "Low.pdf",
            "page_label": "1",
            "text": "lower strength snippet",
            "llm_trulens_score": 0.1,
            "rerank_score": 0.0,
            "vector_score": 0.0,
        },
        {
            "source_id": "file-2",
            "source_name": "High.pdf",
            "page_label": "2",
            "text": "higher strength snippet",
            "llm_trulens_score": 0.8,
            "rerank_score": 0.2,
            "vector_score": 0.1,
        },
    ]
    enriched, refs = assign_fast_source_refs(snippets, strength_ordering=True)
    assert refs[0]["source_name"] == "High.pdf"
    assert refs[0]["id"] == 1
    high_ref = next(item for item in enriched if item["source_name"] == "High.pdf")
    low_ref = next(item for item in enriched if item["source_name"] == "Low.pdf")
    assert int(high_ref["ref_id"]) == 1
    assert int(low_ref["ref_id"]) == 2


def test_build_source_usage_aggregates_retrieved_and_cited_counts() -> None:
    snippets = [
        {
            "source_id": "file-1",
            "source_name": "A.pdf",
            "ref_id": 1,
            "strength_score": 0.8,
        },
        {
            "source_id": "file-1",
            "source_name": "A.pdf",
            "ref_id": 1,
            "strength_score": 0.4,
        },
        {
            "source_id": "file-2",
            "source_name": "B.pdf",
            "ref_id": 2,
            "strength_score": 0.2,
        },
    ]
    refs = [
        {"id": 1, "source_id": "file-1", "source_name": "A.pdf"},
        {"id": 2, "source_id": "file-2", "source_name": "B.pdf"},
    ]
    answer = "Main claim <a class='citation' href='#evidence-1'>[1]</a>."
    usage = build_source_usage(
        snippets_with_refs=snippets,
        refs=refs,
        answer_text=answer,
        enabled=True,
    )
    assert len(usage) == 2
    top = usage[0]
    assert top["source_id"] == "file-1"
    assert top["retrieved_count"] == 2
    assert top["cited_count"] >= 1
    assert 0.0 <= float(top["citation_share"]) <= 1.0


def test_enforce_required_citations_realigns_model_ref_to_matching_evidence() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='3' open>"
        "<summary><i>Evidence [1] - page 3</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> trees absorb water from soil through root systems</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='7'>"
        "<summary><i>Evidence [2] - page 7</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> photosynthesis uses sunlight and chlorophyll</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Trees get water from the soil via their roots [2].",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "href='#evidence-1'" in answer
    assert "data-page='3'" in answer


def test_enforce_required_citations_cites_each_claim_sentence() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='3' open>"
        "<summary><i>Evidence [1] - page 3</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> trees absorb water from soil through roots</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='7'>"
        "<summary><i>Evidence [2] - page 7</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> photosynthesis uses sunlight and chlorophyll</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Trees absorb water from soil through roots. Photosynthesis uses sunlight and chlorophyll.",
        info_html=info_html,
        citation_mode="inline",
    )
    assert answer.count("class='citation'") >= 2
    assert "href='#evidence-1'" in answer
    assert "href='#evidence-2'" in answer


def test_enforce_required_citations_normalizes_visible_numbers_and_hides_duplicates() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='1' open>"
        "<summary><i>Evidence [1] - page 1</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> first reference evidence</div>"
        "</details>"
        "<details class='evidence' id='evidence-4' data-file-id='file-1' data-page='4'>"
        "<summary><i>Evidence [4] - page 4</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> fourth reference evidence</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim one [4]. Claim two [1]. Claim one again [4].",
        info_html=info_html,
        citation_mode="inline",
    )

    assert answer.count("class='citation'") == 2
    assert answer.count(">[1]</a>") == 1
    assert answer.count(">[2]</a>") == 1
    assert ">[4]</a>" not in answer
    assert "href='#evidence-4'" in answer
    assert "href='#evidence-1'" in answer


def test_enforce_required_citations_removes_stale_raw_markers_outside_anchors() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='1' open>"
        "<summary><i>Evidence [1] - page 1</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> first reference evidence</div>"
        "</details>"
        "<details class='evidence' id='evidence-4' data-file-id='file-1' data-page='4'>"
        "<summary><i>Evidence [4] - page 4</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> fourth reference evidence</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim one [4]. Claim two [1]. Stale marker [99]. Claim one again [4].",
        info_html=info_html,
        citation_mode="inline",
    )

    assert "[99]" not in answer
    assert answer.count("class='citation'") == 2
    assert answer.count(">[1]</a>") == 1
    assert answer.count(">[2]</a>") == 1


def test_collect_cited_ref_ids_uses_anchor_target_ids_when_present() -> None:
    answer = (
        "Claim <a class='citation' href='#evidence-4' id='citation-4'>[1]</a> "
        "and <a class='citation' href='#evidence-1' id='citation-1'>[2]</a>."
    )
    assert collect_cited_ref_ids(answer) == [4, 1]
