from api.services.chat.fast_qa import (
    _assess_evidence_sufficiency_with_llm,
    _build_no_relevant_evidence_answer,
    _expand_retrieval_query_for_gap,
    _finalize_retrieved_snippets,
    _rewrite_followup_question_for_retrieval,
    _resolve_contextual_url_targets,
)
from api.services.chat.fast_qa import _annotate_primary_sources, _prioritize_primary_evidence
from api.services.chat.fast_qa_retrieval import (
    _extract_query_terms,
    _extract_target_hosts,
    _matches_target_hosts,
    _placeholder_host_penalty,
    _query_coverage_boost,
    _source_credibility_profile,
    _substantive_text_quality_boost,
    _technical_query_relevance_boost,
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


def test_placeholder_host_penalty_demotes_example_domain() -> None:
    assert _placeholder_host_penalty("https://example.com/ml") < 0
    assert _placeholder_host_penalty("https://localhost:8000/test") < 0
    assert _placeholder_host_penalty("https://axongroup.com/about") == 0.0


def test_substantive_text_quality_boost_prefers_real_paragraph_over_short_fragment() -> None:
    short_fragment = "hello upload test after fix"
    real_paragraph = (
        "Machine learning is a field of artificial intelligence focused on systems that improve from data. "
        "It includes supervised, unsupervised, and reinforcement learning approaches, each with different training objectives."
    )

    assert _substantive_text_quality_boost(text=real_paragraph) > _substantive_text_quality_boost(text=short_fragment)


def test_query_coverage_boost_prefers_chunk_covering_more_query_terms() -> None:
    query_terms = _extract_query_terms("machine learning model training data performance")
    high_coverage = (
        "Machine learning model training depends on data quality and directly affects performance during evaluation."
    )
    low_coverage = "Machine learning can be useful in many domains."

    assert _query_coverage_boost(text=high_coverage, query_terms=query_terms) > _query_coverage_boost(
        text=low_coverage,
        query_terms=query_terms,
    )


def test_source_credibility_profile_prefers_authoritative_and_platform_sources() -> None:
    high_tier, high_boost = _source_credibility_profile(
        source_type="web",
        source_url="https://developers.google.com/machine-learning",
        source_name="https://developers.google.com/machine-learning",
    )
    low_tier, low_boost = _source_credibility_profile(
        source_type="web",
        source_url="https://www.w3schools.com/python/python_ml_getting_started.asp",
        source_name="https://www.w3schools.com/python/python_ml_getting_started.asp",
    )
    platform_tier, platform_boost = _source_credibility_profile(
        source_type="pdf",
        source_url="",
        source_name="internal_report.pdf",
    )

    assert high_tier == "high"
    assert high_boost > 0
    assert low_tier == "low"
    assert low_boost < 0
    assert platform_tier == "platform"
    assert platform_boost > 0


def test_no_relevant_evidence_answer_mentions_target_url() -> None:
    answer = _build_no_relevant_evidence_answer("https://axongroup.com what is this company doing?")
    assert "https://axongroup.com" in answer
    assert "Not visible in indexed content" in answer
    assert "online search" not in answer.lower()
    assert "Maia" in answer


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


def test_no_relevant_evidence_answer_mentions_maia_sources_when_no_url_is_available() -> None:
    answer = _build_no_relevant_evidence_answer("What does the uploaded material say about this topic?")
    assert "Maia files, documents, indexed URLs" in answer


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


def test_finalize_retrieved_snippets_broad_single_pdf_question_preserves_page_diversity(monkeypatch) -> None:
    snippets = [
        {"source_id": "file-1", "source_key": "file-1", "source_name": "Doc.pdf", "page_label": "69", "score": 15.0, "text": "humidity degradation and chloride"},
        {"source_id": "file-1", "source_key": "file-1", "source_name": "Doc.pdf", "page_label": "66", "score": 14.0, "text": "white heat and fused spheres"},
        {"source_id": "file-1", "source_key": "file-1", "source_name": "Doc.pdf", "page_label": "8", "score": 13.0, "text": "balsa wood and copper sulfate paper"},
    ]

    monkeypatch.setattr(
        "api.services.chat.fast_qa._select_relevant_snippets_with_llm",
        lambda **kwargs: [kwargs["snippets"][0]],
    )

    selected, _note, reason, _meta = _finalize_retrieved_snippets(
        question="If this system were deployed in a different environment, what modifications would be required?",
        chat_history=[],
        retrieved_snippets=snippets,
        selected_payload={"1": ["select", ["file-1"], "user-1"]},
        target_urls=[],
        mindmap_focus=None,
        max_keep=6,
    )

    assert reason == ""
    assert len(selected) >= 3
    assert [str(item.get("page_label")) for item in selected[:3]] == ["69", "66", "8"]


def test_finalize_retrieved_snippets_preserves_selected_source_coverage(monkeypatch) -> None:
    snippets = [
        {
            "source_id": "file-1",
            "source_key": "file-1",
            "source_name": "source-a.txt",
            "page_label": "1",
            "score": 9.0,
            "text": "This source says the term machine learning was coined in 1959 by Arthur Samuel.",
        },
        {
            "source_id": "file-2",
            "source_key": "file-2",
            "source_name": "source-b.txt",
            "page_label": "1",
            "score": 8.0,
            "text": "This source says the term machine learning was coined in 1952 in early computing discussions.",
        },
    ]

    monkeypatch.setattr(
        "api.services.chat.fast_qa._select_relevant_snippets_with_llm",
        lambda **kwargs: [kwargs["snippets"][0]],
    )

    selected, _note, reason, _meta = _finalize_retrieved_snippets(
        question="According to the selected Maia sources, when was the term machine learning coined?",
        chat_history=[],
        retrieved_snippets=snippets,
        selected_payload={"1": ["select", ["file-1", "file-2"], "user-1"]},
        target_urls=[],
        mindmap_focus=None,
        max_keep=4,
    )

    assert reason == ""
    covered = {str(item.get("source_id") or item.get("source_key") or "") for item in selected}
    assert "file-1" in covered
    assert "file-2" in covered


def test_technical_query_relevance_boost_prefers_balance_equation_over_nomenclature() -> None:
    query = "Derive the full component material balance for component i across the distillation column, then extend it to include vapor and liquid feeds separately."
    terms = _extract_query_terms(query)
    formula_text = (
        "Component material balance across the distillation column: "
        "$$ Fx_{iF}=Dx_{iD}+Bx_{iB} $$ "
        "With separate vapor and liquid feeds, the balance includes feed vapor and liquid stream terms."
    )
    nomenclature_text = (
        "## Nomenclature y mole fraction of vapor phase z mole fraction of liquid-vapor mixture "
        "1, 2, 3... component labels and symbols used throughout the chapter."
    )

    formula_boost = _technical_query_relevance_boost(
        query_lower=query.lower(),
        text=formula_text,
        query_terms=terms,
    )
    nomenclature_boost = _technical_query_relevance_boost(
        query_lower=query.lower(),
        text=nomenclature_text,
        query_terms=terms,
    )

    assert formula_boost > 0
    assert nomenclature_boost < 0
    assert formula_boost > nomenclature_boost


def test_technical_query_relevance_boost_penalizes_short_figure_caption() -> None:
    query = "Derive the component balance equation for the distillation column."
    terms = _extract_query_terms(query)
    caption_text = "Figure 1.1."
    equation_text = "The material balance is $$ Fx_{iF}=Dx_{iD}+Bx_{iB} $$ for the distillation column."

    caption_boost = _technical_query_relevance_boost(
        query_lower=query.lower(),
        text=caption_text,
        query_terms=terms,
    )
    equation_boost = _technical_query_relevance_boost(
        query_lower=query.lower(),
        text=equation_text,
        query_terms=terms,
    )

    assert caption_boost < 0
    assert equation_boost > caption_boost
