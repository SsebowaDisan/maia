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
    assert resolve_required_citation_mode("footnote") == "footnote"


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
    assert "Evidence:" in answer
    assert "class='citation'" in answer
    assert "href='#evidence-1'" in answer


def test_append_required_citation_suffix_adds_internal_trace_when_refs_missing() -> None:
    answer = append_required_citation_suffix(
        answer="Answer without refs",
        info_html="",
    )
    assert "Evidence: internal execution trace" in answer
