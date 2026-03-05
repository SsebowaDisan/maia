from api.services.chat.fast_qa import (
    _assess_evidence_sufficiency_with_llm,
    _build_no_relevant_evidence_answer,
    _expand_retrieval_query_for_gap,
    _rewrite_followup_question_for_retrieval,
    _resolve_contextual_url_targets,
)
from api.services.chat.fast_qa import _annotate_primary_sources, _prioritize_primary_evidence
from api.services.chat.fast_qa_retrieval import (
    _extract_query_terms,
    _extract_target_hosts,
    _matches_target_hosts,
)


def test_extract_query_terms_is_dynamic_and_deduplicated() -> None:
    terms = _extract_query_terms("What does Axon Group do and what does Axon Group build in 2026?")
    assert "axon" in terms
    assert "group" in terms
    assert "what" in terms
    assert terms.count("axon") == 1
    assert "2026" not in terms


def test_extract_target_hosts_normalizes_hosts() -> None:
    hosts = _extract_target_hosts("Analyze https://www.axongroup.com/about and compare with https://blog.axongroup.com")
    assert "axongroup.com" in hosts
    assert "blog.axongroup.com" in hosts


def test_matches_target_hosts_uses_source_name_and_metadata() -> None:
    assert _matches_target_hosts(
        source_name="Indexed file",
        metadata={"page_url": "https://axongroup.com/products"},
        target_hosts={"axongroup.com"},
    )
    assert _matches_target_hosts(
        source_name="https://www.axongroup.com/contact",
        metadata={},
        target_hosts={"axongroup.com"},
    )


def test_matches_target_hosts_rejects_unrelated_sources() -> None:
    assert not _matches_target_hosts(
        source_name="docs/company_agent_end_to_end_roadmap.md",
        metadata={"page_url": "https://example.com/about"},
        target_hosts={"axongroup.com"},
    )


def test_no_relevant_evidence_answer_mentions_target_url() -> None:
    answer = _build_no_relevant_evidence_answer("https://axongroup.com what is this company doing?")
    assert "https://axongroup.com" in answer
    assert "Not visible in indexed content" in answer


def test_no_relevant_evidence_answer_uses_target_url_override() -> None:
    answer = _build_no_relevant_evidence_answer(
        "what is their contact details?",
        target_url="https://axongroup.com/about-axon",
    )
    assert "https://axongroup.com/about-axon" in answer


def test_no_relevant_evidence_answer_respects_response_language() -> None:
    answer = _build_no_relevant_evidence_answer(
        "Que hace esta empresa?",
        target_url="https://axongroup.com/about-axon",
        response_language="es",
    )
    assert "https://axongroup.com/about-axon" in answer
    assert "No pude encontrar evidencia" in answer


def test_resolve_contextual_url_targets_uses_recent_history_when_llm_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.chat.fast_qa._resolve_fast_qa_llm_config",
        lambda: ("", "https://api.openai.com/v1", "gpt-4o-mini", "missing"),
    )
    targets = _resolve_contextual_url_targets(
        question="what is their contact details",
        chat_history=[
            ["https://axongroup.com what is this company doing?", "summary answer"],
            ["Thanks", "You're welcome"],
        ],
    )
    assert targets == ["https://axongroup.com"]


def test_rewrite_followup_question_appends_primary_url_when_llm_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.chat.fast_qa._resolve_fast_qa_llm_config",
        lambda: ("", "https://api.openai.com/v1", "gpt-4o-mini", "missing"),
    )
    rewritten, is_follow_up, reason = _rewrite_followup_question_for_retrieval(
        question="what is their contact details?",
        chat_history=[["https://axongroup.com what is this company doing?", "summary answer"]],
        target_urls=["https://axongroup.com"],
    )
    assert "https://axongroup.com" in rewritten
    assert is_follow_up is True
    assert "llm-unavailable" in reason


def test_expand_retrieval_query_appends_primary_url_when_llm_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.chat.fast_qa._resolve_fast_qa_llm_config",
        lambda: ("", "https://api.openai.com/v1", "gpt-4o-mini", "missing"),
    )
    expanded, reason = _expand_retrieval_query_for_gap(
        question="what is their contact details?",
        current_query="what is their contact details",
        chat_history=[["https://axongroup.com what is this company doing?", "summary answer"]],
        snippets=[],
        insufficiency_reason="No direct contact details in snippets.",
        target_urls=["https://axongroup.com"],
    )
    assert "https://axongroup.com" in expanded
    assert "llm-unavailable" in reason


def test_assess_evidence_sufficiency_requires_primary_when_requested() -> None:
    sufficient, confidence, reason = _assess_evidence_sufficiency_with_llm(
        question="what is their contact details?",
        chat_history=[["https://axongroup.com what is this company doing?", "summary answer"]],
        snippets=[
            {
                "source_name": "docs/internal.md",
                "text": "internal architecture notes",
                "is_primary_source": False,
            }
        ],
        primary_source_note="Primary source target from user or conversation context: https://axongroup.com",
        require_primary_source=True,
    )
    assert sufficient is False
    assert confidence == 0.0
    assert "primary-source" in reason.lower()


def test_annotate_primary_sources_marks_url_targets_as_primary() -> None:
    snippets = [
        {
            "source_id": "web-1",
            "source_name": "https://axongroup.com/about",
            "source_url": "https://axongroup.com/about",
            "score": 2.0,
        },
        {
            "source_id": "file-1",
            "source_name": "docs/company_agent_end_to_end_roadmap.md",
            "score": 6.0,
        },
    ]
    annotated, note = _annotate_primary_sources(
        question="https://axongroup.com what is this company doing?",
        snippets=snippets,
        selected_payload={},
    )
    assert annotated[0]["is_primary_source"] is True
    assert "axongroup.com" in note


def test_annotate_primary_sources_marks_selected_file_as_primary() -> None:
    snippets = [
        {"source_id": "file-primary", "source_name": "Proposal.pdf", "score": 1.0},
        {"source_id": "file-secondary", "source_name": "Other.pdf", "score": 10.0},
    ]
    annotated, note = _annotate_primary_sources(
        question="Summarize this PDF.",
        snippets=snippets,
        selected_payload={"1": ["select", ["file-primary"], "user-1"]},
    )
    assert annotated[0]["source_id"] == "file-primary"
    assert annotated[0]["is_primary_source"] is True
    assert "file-primary" in note


def test_annotate_primary_sources_does_not_use_selected_file_as_primary_for_url_prompt() -> None:
    snippets = [
        {"source_id": "file-primary", "source_name": "Proposal.pdf", "score": 10.0},
        {
            "source_id": "web-1",
            "source_name": "https://axongroup.com/about",
            "source_url": "https://axongroup.com/about",
            "score": 1.0,
        },
    ]
    annotated, _note = _annotate_primary_sources(
        question="https://axongroup.com what is this company doing?",
        snippets=snippets,
        selected_payload={"1": ["select", ["file-primary"], "user-1"]},
    )
    by_id = {str(row.get("source_id")): row for row in annotated}
    assert bool(by_id["web-1"]["is_primary_source"]) is True
    assert bool(by_id["file-primary"]["is_primary_source"]) is False


def test_prioritize_primary_evidence_keeps_secondary_sources_secondary() -> None:
    snippets = [
        {"source_name": "Primary.pdf", "is_primary_source": True, "score": 1.0},
        {"source_name": "Other-1.pdf", "is_primary_source": False, "score": 9.0},
        {"source_name": "Other-2.pdf", "is_primary_source": False, "score": 8.0},
        {"source_name": "Other-3.pdf", "is_primary_source": False, "score": 7.0},
        {"source_name": "Other-4.pdf", "is_primary_source": False, "score": 6.0},
    ]
    kept = _prioritize_primary_evidence(snippets, max_keep=5)
    assert kept[0]["is_primary_source"] is True
    assert sum(1 for row in kept if not bool(row.get("is_primary_source"))) <= 2


def test_prioritize_primary_evidence_can_disable_secondary_sources() -> None:
    snippets = [
        {"source_name": "Primary.pdf", "is_primary_source": True, "score": 1.0},
        {"source_name": "Other-1.pdf", "is_primary_source": False, "score": 9.0},
        {"source_name": "Other-2.pdf", "is_primary_source": False, "score": 8.0},
    ]
    kept = _prioritize_primary_evidence(snippets, max_keep=5, max_secondary=0)
    assert all(bool(row.get("is_primary_source")) for row in kept)
