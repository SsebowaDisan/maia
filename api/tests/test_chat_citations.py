from api.services.chat.citations import (
    append_required_citation_suffix,
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
