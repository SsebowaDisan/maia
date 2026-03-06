import html as html_lib
import re

from api.services.chat.citations import (
    assign_fast_source_refs,
    append_required_citation_suffix,
    build_source_usage,
    build_fast_info_html,
    collect_cited_ref_ids,
    enforce_required_citations,
    normalize_info_evidence_html,
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


def test_append_required_citation_suffix_normalizes_legacy_mark_anchor_ids() -> None:
    info_html = (
        "<details class='evidence' id='evidence-2' data-file-id='file-2' data-page='9' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> legacy anchor evidence</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer="Claim with legacy anchor <a class='citation' href='#' id='mark-2'>【2】</a>.",
        info_html=info_html,
    )
    assert "href='#evidence-2'" in answer
    assert "id='citation-2'" in answer
    assert "data-file-id='file-2'" in answer
    assert "data-page='9'" in answer
    assert "data-citation-number='1'" in answer
    assert ">[1]</a>" in answer


def test_append_required_citation_suffix_strips_stale_plain_markers_when_anchor_exists() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> citation evidence</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer="Claim [1] <a class='citation' href='#evidence-1' id='citation-1'>[1]</a> stale [99].",
        info_html=info_html,
    )
    assert "[99]" not in answer
    assert answer.count("class='citation'") == 1
    assert answer.count(">[1]</a>") == 1


def test_append_required_citation_suffix_dedupes_plain_and_linked_answer_passes() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> citation evidence</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='3' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> more citation evidence</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer=(
            "The PDF discusses a chat shell with sidebar and composer 【1】. "
            "It emphasizes deterministic navigation 【2】."
            "The PDF discusses a chat shell with sidebar and composer "
            "<a class='citation' href='#' id='mark-1'>【1】</a>. "
            "It emphasizes deterministic navigation "
            "<a class='citation' href='#' id='mark-2'>【2】</a>."
        ),
        info_html=info_html,
    )
    assert answer.count("class='citation'") == 2
    assert answer.count("The PDF discusses a chat shell with sidebar and composer") == 1
    assert "href='#evidence-1'" in answer
    assert "href='#evidence-2'" in answer


def test_append_required_citation_suffix_paragraphizes_dense_answer_without_forcing_template() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='f1' data-page='1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> first sentence evidence</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='f1' data-page='2' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> second sentence evidence</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer=(
            "This document explains the architecture of a production-ready customer support "
            "application and clarifies the deterministic flow that keeps AI actions predictable [1]. "
            "It describes how the knowledge base search is refactored and seeded so retrieval returns "
            "stable excerpts for responses across repeated runs [2]. "
            "The guide also covers configuration updates and error handling patterns so OpenAI API "
            "failures can be surfaced and recovered without breaking the user journey [1]. "
            "It adds testing guidance that verifies integrity constraints and validates that each "
            "component can be evolved independently in future iterations [2]. "
            "Overall, it frames a practical implementation path for teams that want maintainable support "
            "tooling with auditable evidence-backed outputs [1]."
        ),
        info_html=info_html,
    )
    assert "## Summary" not in answer
    assert "## Key Details" not in answer
    assert "\n\n" in answer
    assert "class='citation'" in answer


def test_append_required_citation_suffix_keeps_three_sentence_answer_adaptive() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='f1' data-page='1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> app architecture and deterministic flow</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='f1' data-page='2' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> knowledge base workflow and error handling</div>"
        "</details>"
        "<details class='evidence' id='evidence-3' data-file-id='f1' data-page='3' open>"
        "<summary><i>Evidence [3]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> testing and maintainability guidance</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer=(
            "The document explains a professional-grade support application architecture with a deterministic "
            "execution flow for AI-driven features [1][2]. "
            "It details knowledge base workflow improvements, UI integration, and resilient OpenAI API error "
            "handling to keep interactions stable [2]. "
            "It also highlights testing and maintainability practices that help teams extend the app safely [3]."
        ),
        info_html=info_html,
    )
    assert "## Summary" not in answer
    assert "## Key Details" not in answer
    assert answer.count("class='citation'") >= 2


def test_append_required_citation_suffix_does_not_force_template_for_two_sentences() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='f1' data-page='1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> architecture and deterministic flow</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='f1' data-page='2' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> workflow and testing guidance</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer=(
            "The guide explains architecture and deterministic flow for the support app [1]. "
            "It also summarizes workflow and testing guidance for maintainability [2]."
        ),
        info_html=info_html,
    )
    assert "## Summary" not in answer
    assert "## Key Details" not in answer
    assert answer.count("class='citation'") >= 2


def test_append_required_citation_suffix_does_not_force_template_for_single_sentence() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='f1' data-page='1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> concise architecture summary</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer="Concise architecture summary for the support app [1].",
        info_html=info_html,
    )
    assert "## Summary" not in answer
    assert "## Key Details" not in answer
    assert "class='citation'" in answer


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


def test_enforce_required_citations_adds_source_url_from_details_attribute() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-source-url='https://axongroup.com/about' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> company overview</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim supported by source [1].",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "data-source-url='https://axongroup.com/about'" in answer


def test_enforce_required_citations_adds_source_url_from_link_block() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> company overview</div>"
        "<div class='evidence-content'><b>Link:</b> "
        "<a href='https://axongroup.com/about' target='_blank' rel='noopener noreferrer'>https://axongroup.com/about</a>"
        "</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim supported by source [1].",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "data-source-url='https://axongroup.com/about'" in answer


def test_enforce_required_citations_does_not_break_markdown_links_with_url_dots() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-source-url='https://axongroup.com/contact' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> contact page includes form and channels</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="You can use [Axon contact](https://axongroup.com/contact) for inquiries.",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "https://axongroup.com/contact" in answer
    assert "https://axongroup. <a " not in answer
    assert "class='citation'" in answer


def test_enforce_required_citations_repositions_prelinked_end_cluster_to_claim_level() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> first claim evidence sentence</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='3' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> second claim deterministic language sentence</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer=(
            "First claim evidence sentence. "
            "Second claim deterministic language sentence. "
            "Third summary sentence "
            "<a class='citation' href='#' id='mark-1'>【1】</a>"
            "<a class='citation' href='#' id='mark-2'>【2】</a>."
        ),
        info_html=info_html,
        citation_mode="inline",
    )
    assert "href='#evidence-1'" in answer
    assert "href='#evidence-2'" in answer
    assert answer.count("class='citation'") == 2
    assert "Third summary sentence <a " not in answer


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


def test_append_required_citation_suffix_sets_canonical_data_evidence_id() -> None:
    info_html = (
        "<details class='evidence' id='evidence-2' data-file-id='file-2' data-page='6' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> canonical ref payload</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer="Claim with marker [2].",
        info_html=info_html,
    )
    assert "href='#evidence-2'" in answer
    assert "data-evidence-id='evidence-2'" in answer


def test_enforce_required_citations_realigns_out_of_range_markers_to_clickable_refs() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> first evidence sentence</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> second evidence sentence</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim text cites unavailable marker [9].",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "[9]" not in answer
    assert "class='citation'" in answer
    assert "data-evidence-id='evidence-" in answer
    assert ("href='#evidence-1'" in answer) or ("href='#evidence-2'" in answer)


def test_enforce_required_citations_realigns_out_of_range_prelinked_anchor() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='1' open>"
        "<summary><i>Evidence [1]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> first evidence sentence</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='2' open>"
        "<summary><i>Evidence [2]</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> second evidence sentence</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="Claim <a class='citation' href='#' id='mark-9'>【9】</a>.",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "mark-9" not in answer
    assert "[9]" not in answer
    assert "class='citation'" in answer
    assert "data-evidence-id='evidence-" in answer


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


def test_build_fast_info_html_emits_data_source_url_attribute_when_available() -> None:
    info_html = build_fast_info_html(
        [
            {
                "ref_id": 1,
                "source_id": "url-1",
                "source_name": "https://axongroup.com",
                "source_url": "https://axongroup.com/about",
                "text": "Evidence text",
            }
        ]
    )
    assert "data-source-url='https://axongroup.com/about'" in info_html
    assert "<b>Link:</b>" in info_html


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


def test_assign_fast_source_refs_prioritizes_primary_source_before_stronger_secondary() -> None:
    snippets = [
        {
            "source_id": "file-1",
            "source_name": "Primary.pdf",
            "page_label": "1",
            "text": "primary snippet",
            "is_primary_source": True,
            "llm_trulens_score": 0.1,
            "rerank_score": 0.0,
            "vector_score": 0.0,
        },
        {
            "source_id": "file-2",
            "source_name": "Secondary.pdf",
            "page_label": "2",
            "text": "secondary snippet",
            "is_primary_source": False,
            "llm_trulens_score": 0.95,
            "rerank_score": 0.4,
            "vector_score": 0.3,
        },
    ]
    _enriched, refs = assign_fast_source_refs(snippets, strength_ordering=True)
    assert refs[0]["source_name"] == "Primary.pdf"
    assert bool(refs[0].get("is_primary_source")) is True


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


def test_enforce_required_citations_maps_command_style_claims_to_matching_evidence() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='3' open>"
        "<summary><i>Evidence [1] - page 3</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> n3 app.ai check verifies the app compiles before smoke tests</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='8'>"
        "<summary><i>Evidence [2] - page 8</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> start_conversation adds a system message and initializes a new thread</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer=(
            "Use n3 app.ai check before running smoke tests. "
            "Use start_conversation to initialize the conversation thread."
        ),
        info_html=info_html,
        citation_mode="inline",
    )
    assert "href='#evidence-1'" in answer
    assert "href='#evidence-2'" in answer


def test_enforce_required_citations_does_not_force_unrelated_inline_ref_for_multi_source() -> None:
    info_html = (
        "<details class='evidence' id='evidence-1' data-file-id='file-1' data-page='1' open>"
        "<summary><i>Evidence [1] - page 1</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> trees absorb water from roots</div>"
        "</details>"
        "<details class='evidence' id='evidence-2' data-file-id='file-1' data-page='2'>"
        "<summary><i>Evidence [2] - page 2</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> chlorophyll supports photosynthesis</div>"
        "</details>"
    )
    answer = enforce_required_citations(
        answer="This line has no overlap with any evidence phrase.",
        info_html=info_html,
        citation_mode="inline",
    )
    assert "This line has no overlap with any evidence phrase. <a " not in answer
    assert "Evidence: <a " in answer


def test_enforce_required_citations_normalizes_visible_numbers_and_preserves_claim_level_repeats() -> None:
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

    assert answer.count("class='citation'") >= 3
    assert answer.count(">[1]</a>") >= 2
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
    assert answer.count("class='citation'") >= 3
    assert answer.count(">[1]</a>") >= 2
    assert answer.count(">[2]</a>") == 1


def test_collect_cited_ref_ids_uses_anchor_target_ids_when_present() -> None:
    answer = (
        "Claim <a class='citation' href='#evidence-4' id='citation-4'>[1]</a> "
        "and <a class='citation' href='#evidence-1' id='citation-1'>[2]</a>."
    )
    assert collect_cited_ref_ids(answer) == [4, 1]


def test_normalize_info_evidence_html_assigns_missing_evidence_ids_and_source_url() -> None:
    info_html = (
        "<details class='evidence' open>"
        "<summary><i>Website source</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> Axon Group company profile</div>"
        "<div class='evidence-content'><b>Link:</b> "
        "<a href='https://axongroup.com/about' target='_blank' rel='noopener noreferrer'>https://axongroup.com/about</a>"
        "</div>"
        "</details>"
    )
    normalized = normalize_info_evidence_html(info_html)
    assert "id='evidence-1'" in normalized
    assert "data-source-url='https://axongroup.com/about'" in normalized


def test_append_required_citation_suffix_handles_legacy_evidence_blocks_without_ids() -> None:
    info_html = (
        "<details class='evidence' open>"
        "<summary><i>Website source</i></summary>"
        "<div class='evidence-content'><b>Extract:</b> Axon Group company profile</div>"
        "<div class='evidence-content'><b>Link:</b> "
        "<a href='https://axongroup.com/about' target='_blank' rel='noopener noreferrer'>https://axongroup.com/about</a>"
        "</div>"
        "</details>"
    )
    answer = append_required_citation_suffix(
        answer="Axon Group provides industrial solutions [1].",
        info_html=info_html,
    )
    assert "class='citation'" in answer
    assert "href='#evidence-1'" in answer
    assert "data-source-url='https://axongroup.com/about'" in answer


def test_build_fast_info_html_ignores_artifact_source_urls() -> None:
    info_html = build_fast_info_html(
        [
            {
                "ref_id": 1,
                "source_id": "web-1",
                "source_name": "https://axongroup.com/Extract",
                "source_url": "https://axongroup.com/Extract",
                "text": "Industrial solutions square",
            }
        ]
    )
    assert "data-source-url=" not in info_html
    assert "<b>Link:</b>" not in info_html


def test_build_fast_info_html_compacts_extract_for_highlight_panel() -> None:
    info_html = build_fast_info_html(
        [
            {
                "ref_id": 1,
                "source_id": "file-1",
                "source_name": "Doc.pdf",
                "page_label": "4",
                "text": ("command output details " * 90).strip(),
            }
        ]
    )
    extract_match = re.search(
        r"<div class='evidence-content'><b>Extract:</b>\s*([\s\S]*?)</div>",
        info_html,
        flags=re.IGNORECASE,
    )
    assert extract_match is not None
    extract = html_lib.unescape(extract_match.group(1).strip())
    assert len(extract) <= 523
    assert extract.endswith("...")
