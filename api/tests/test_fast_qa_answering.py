from api.services.chat.fast_qa_turn_sections.answering import (
    _build_evidence_limited_answer,
    _build_model_failure_answer,
    _build_partial_scope_answer,
    _requires_broad_grounding,
    _build_unsupported_by_source_answer,
    _question_support_ratio,
    build_answer_phase,
)


def test_build_evidence_limited_answer_surfaces_visible_points_and_limits_scope() -> None:
    answer = _build_evidence_limited_answer(
        question="What does the source show?",
        snippets_with_refs=[
            {
                "ref_id": 1,
                "text": "The document derives steady-state component balances for distillation columns.",
            },
            {
                "ref_id": 2,
                "text": "It does not discuss environmental hardening or ambient deployment constraints.",
            },
        ],
        evidence_reason="Selected evidence is too narrow for a broad deployment answer.",
    )

    assert "does not provide enough evidence" in answer
    assert "Visible evidence is limited to" in answer
    assert "[1]" in answer
    assert "[2]" in answer
    assert "not supported by the indexed content" in answer


def test_question_support_ratio_is_low_for_environment_question_against_distillation_math() -> None:
    ratio = _question_support_ratio(
        question="If this system were deployed in a different environment such as high humidity or extreme temperatures, what modifications would be required?",
        snippets_with_refs=[
            {
                "text": "The document derives steady-state component balances and extends them to vapor and liquid feed streams in multicomponent distillation.",
            },
            {
                "text": "It focuses on optimal sequencing of separation units and algebraic balance relations.",
            },
        ],
    )

    assert ratio < 0.34


def test_question_support_ratio_is_high_when_environment_terms_are_supported() -> None:
    ratio = _question_support_ratio(
        question="If this system were deployed in a different environment such as high humidity or extreme temperatures, what modifications would be required?",
        snippets_with_refs=[
            {
                "text": "High humidity requires sealed enclosures and corrosion-resistant materials, while extreme temperatures require insulation and thermal expansion allowances.",
            }
        ],
    )

    assert ratio >= 0.34


def test_requires_broad_grounding_is_false_for_narrow_derivation_question() -> None:
    assert (
        _requires_broad_grounding(
            "Derive the full component material balance for component i across the distillation column, then extend it to include vapor and liquid feeds separately."
        )
        is False
    )


def test_model_failure_answer_is_evidence_limited() -> None:
    answer = _build_model_failure_answer(
        question="What is the full derivation?",
        snippets_with_refs=[
            {
                "ref_id": 1,
                "text": "The source derives steady-state material balances for distillation columns.",
            }
        ]
    )

    assert "answer model was unavailable" in answer
    assert "[1]" in answer
    assert "not supported by the indexed content" in answer


def test_build_evidence_limited_answer_sanitizes_html_and_prefers_relevant_text() -> None:
    answer = _build_evidence_limited_answer(
        question="Derive the material balance for vapor and liquid feeds.",
        snippets_with_refs=[
            {"ref_id": 1, "text": "<div><img src='x' /></div> Figure 4.4 reversible distillation.</div>"},
            {"ref_id": 2, "text": "The total material balance is extended by adding separate vapor and liquid feed streams to the component equations."},
        ],
        evidence_reason="The answer model was unavailable for this turn, so Maia is limiting the response to directly visible evidence only.",
    )

    assert "<img" not in answer
    assert "Figure 4.4" not in answer
    assert "[2]" in answer


def test_build_evidence_limited_answer_prefers_formula_excerpt_for_derivation_question() -> None:
    answer = _build_evidence_limited_answer(
        question="Derive the full component material balance for component i across the distillation column, then extend it to include vapor and liquid feeds separately.",
        snippets_with_refs=[
            {"ref_id": 1, "text": "when the distillate is removed in form of vapor and part of the distillate is liquid."},
            {"ref_id": 2, "text": "Fx_{iF}=Dx_{iD}+Bx_{iB} and separate vapor and liquid feed streams are introduced in the component balance equations for the distillation column."},
        ],
        evidence_reason="The answer model was unavailable for this turn, so Maia is limiting the response to directly visible evidence only.",
    )

    assert "Fx_{iF}=Dx_{iD}+Bx_{iB}" in answer
    assert "[2]" in answer


def test_unsupported_by_source_answer_stays_narrow() -> None:
    answer = _build_unsupported_by_source_answer(evidence_reason="Evidence is off-topic.")

    assert "does not provide directly relevant evidence" in answer
    assert "not extrapolating beyond the source" in answer


def test_build_partial_scope_answer_calls_out_partial_selected_coverage() -> None:
    answer = _build_partial_scope_answer(
        question="Summarize the selected Maia sources.",
        snippets_with_refs=[
            {
                "ref_id": 1,
                "text": "Machine learning systems learn patterns from data and improve performance with experience.",
            }
        ],
        evidence_reason="Only one selected source contained matching indexed evidence.",
        selected_scope_count=3,
        covered_scope_count=1,
    )

    assert "Only 1 of 3 selected Maia sources surfaced directly relevant evidence" in answer
    assert "matching indexed evidence" in answer
    assert "[1]" in answer


def test_build_partial_scope_answer_suppresses_trivial_visible_excerpt() -> None:
    answer = _build_partial_scope_answer(
        question="Summarize the selected Maia sources about machine learning.",
        snippets_with_refs=[
            {
                "ref_id": 1,
                "text": "hello upload test after fix",
            }
        ],
        evidence_reason="Evidence does not contain machine learning content.",
        selected_scope_count=2,
        covered_scope_count=1,
    )

    assert "Only 1 of 2 selected Maia sources surfaced directly relevant evidence" in answer
    assert "hello upload test after fix" not in answer.lower()
    assert "usable evidence is limited to" not in answer.lower()


def test_build_answer_phase_keeps_grounded_path_when_model_answer_missing() -> None:
    retrieval = {
        "message": "If this system were deployed in a different environment, what modifications would be required?",
        "snippets": [
            {
                "text": "The source derives steady-state material balances for distillation columns.",
                "page_label": "12",
                "score": 0.8,
                "source_id": "file-1",
                "source_name": "distillation.pdf",
            }
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 1,
        "covered_scope_count": 1,
        "selected_scope_ids": ["file-1"],
        "all_project_sources": ["distillation.pdf"],
        "focus_meta": {},
        "evidence_confidence": 0.4,
        "evidence_reason": "Evidence is narrow.",
    }

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: None,
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {},
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: None,
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: (
                [{**snippets[0], "ref_id": 1, "ref": "1"}],
                [{"id": 1, "label": "1"}],
            ),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    assert "does not provide directly relevant evidence" in answering["answer"]
    assert answering["snippets_with_refs"] == []


def test_build_answer_phase_does_not_narrow_precise_multi_page_derivation_question() -> None:
    retrieval = {
        "message": "Derive the full component material balance for component i across the distillation column, then extend it to include vapor and liquid feeds separately.",
        "snippets": [
            {
                "text": "Fx_{iF}=Dx_{iD}+Bx_{iB} and separate vapor and liquid feed streams are introduced in the balance equations.",
                "page_label": "21",
                "score": 0.9,
                "source_id": "file-1",
                "source_name": "distillation.pdf",
            },
            {
                "text": "Liquid and vapor feeds alter the component balances through additional stream terms in the distillation column.",
                "page_label": "40",
                "score": 0.88,
                "source_id": "file-1",
                "source_name": "distillation.pdf",
            },
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 1,
        "covered_scope_count": 1,
        "selected_scope_ids": ["file-1"],
        "all_project_sources": ["distillation.pdf"],
        "focus_meta": {},
        "evidence_confidence": 0.5,
        "evidence_reason": "Check failed; fail-open.",
    }

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: None,
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {},
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: None,
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: (
                [
                    {**snippets[0], "ref_id": 1, "ref": "1"},
                    {**snippets[1], "ref_id": 1, "ref": "1"},
                ],
                [{"id": 1, "label": "1"}],
            ),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    assert "does not provide directly relevant evidence" not in answering["answer"]
    assert "answer model was unavailable" in answering["answer"]
    assert len(answering["snippets_with_refs"]) == 2


def test_build_answer_phase_disables_general_knowledge_fallback_for_rag() -> None:
    retrieval = {
        "message": "Summarize the selected sources only.",
        "snippets": [],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 2,
        "covered_scope_count": 0,
        "selected_scope_ids": ["file-1", "file-2"],
        "all_project_sources": [],
        "focus_meta": {},
        "evidence_confidence": 0.0,
        "evidence_reason": "No directly relevant evidence was found in Maia files, documents, or indexed URLs for this request.",
    }
    captured: dict[str, object] = {"model_called": False}

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: captured.update(
            {
                "model_called": True,
                "allow_general_knowledge": kwargs.get("allow_general_knowledge"),
            }
        )
        or "",
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {},
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: None,
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: ([], []),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    assert captured["model_called"] is False
    assert answering["answer"] == "no evidence"


def test_build_answer_phase_narrows_partial_selected_scope_for_rag() -> None:
    retrieval = {
        "message": "Summarize the selected Maia sources.",
        "snippets": [
            {
                "text": "Machine learning is a field of study that gives computers the ability to learn from data.",
                "page_label": "1",
                "score": 0.82,
                "source_id": "file-1",
                "source_name": "notes.txt",
                "source_type": "file",
            }
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 3,
        "covered_scope_count": 1,
        "selected_scope_ids": ["file-1", "file-2", "file-3"],
        "selected_scope_sources": [
            {"file_id": "file-1", "label": "notes.txt", "source_type": "file", "url": ""},
            {"file_id": "file-2", "label": "appendix.txt", "source_type": "file", "url": ""},
            {"file_id": "file-3", "label": "reference-url", "source_type": "web", "url": "https://example.com/ml"},
        ],
        "all_project_sources": ["notes.txt", "appendix.txt", "https://example.com/ml"],
        "focus_meta": {},
        "evidence_confidence": 0.61,
        "evidence_reason": "Only one selected source contained matching indexed evidence.",
    }

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: "Machine learning is the study of data-driven pattern learning [1].",
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {},
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [{"label": "notes.txt", "source_type": "file", "file_id": "file-1", "url": ""}],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: None,
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: (
                [{**snippets[0], "ref_id": 1, "ref": "1"}],
                [{"id": 1, "label": "1"}],
            ),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    assert "Only 1 of 3 selected Maia sources surfaced directly relevant evidence" in answering["answer"]
    assert answering["info_panel"]["answer_origin"] == "partial_scope_grounded_fallback"


def test_build_answer_phase_surfaces_evidence_conflict_summary_for_rag() -> None:
    emitted: list[dict[str, object]] = []
    retrieval = {
        "message": "Compare the selected Maia sources.",
        "snippets": [
            {
                "text": "Source A says revenue was 10M.",
                "page_label": "1",
                "score": 0.9,
                "source_id": "file-1",
                "source_name": "report-a.pdf",
                "source_type": "pdf",
                "credibility_tier": "high",
            },
            {
                "text": "Source B says revenue was 8M.",
                "page_label": "2",
                "score": 0.88,
                "source_id": "file-2",
                "source_name": "report-b.pdf",
                "source_type": "pdf",
                "credibility_tier": "platform",
            },
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 2,
        "covered_scope_count": 2,
        "selected_scope_ids": ["file-1", "file-2"],
        "selected_scope_sources": [],
        "all_project_sources": ["report-a.pdf", "report-b.pdf"],
        "focus_meta": {},
        "evidence_confidence": 0.92,
        "evidence_reason": "Multiple selected sources support different values.",
    }

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: "Revenue appears as 10M [1] and 8M [2].",
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [
            {"source_name": "report-a.pdf", "source_type": "pdf", "credibility_tier": "high", "cited_count": 1, "retrieved_count": 1, "citation_share": 0.5, "max_strength_score": 0.8, "avg_strength_score": 0.8},
            {"source_name": "report-b.pdf", "source_type": "pdf", "credibility_tier": "platform", "cited_count": 1, "retrieved_count": 1, "citation_share": 0.5, "max_strength_score": 0.9, "avg_strength_score": 0.9},
        ],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {
            "claims_evaluated": 1,
            "supported_claims": 0,
            "contradicted_claims": 1,
            "mixed_claims": 0,
            "rows": [
                {
                    "claim": "Revenue appears as 10M and 8M.",
                    "ref_ids": [1, 2],
                    "status": "contradicted",
                    "support_votes": 0,
                    "contradiction_votes": 1,
                }
            ],
        },
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [
            {"label": "report-a.pdf", "source_type": "pdf", "credibility_tier": "high", "file_id": "file-1", "url": ""},
            {"label": "report-b.pdf", "source_type": "pdf", "credibility_tier": "platform", "file_id": "file-2", "url": ""},
        ],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: emitted.append(kwargs),
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: (
                [
                    {**snippets[0], "ref_id": 1, "ref": "1"},
                    {**snippets[1], "ref_id": 2, "ref": "2"},
                ],
                [
                    {"id": 1, "label": "1", "credibility_tier": "high"},
                    {"id": 2, "label": "2", "credibility_tier": "platform"},
                ],
            ),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    summary = answering["info_panel"]["evidence_conflict_summary"]
    assert summary["status"] == "contradicted"
    assert summary["highest_credibility_tier"] == "platform"
    assert summary["has_credibility_preference"] is True
    assert "Prefer the higher-credibility evidence" in summary["message"]
    assert answering["info_panel"]["answer_origin"] == "conflict_aware_grounded_synthesis"
    assert "## Agreed Evidence" in answering["answer"]
    assert "## Conflicting Evidence" in answering["answer"]
    assert "## Conclusion" in answering["answer"]
    assert "Conflict: Revenue appears as 10M and 8M. [1] [2]" in answering["answer"]
    assert "prefer the higher-credibility evidence" in answering["answer"].lower()
    assert "Revenue appears as 10M and 8M." not in answering["answer"].split("## Conclusion", 1)[1]
    assert any(str(row.get("event_type")) == "document_conflict_detected" for row in emitted)


def test_build_answer_phase_infers_conflict_from_conflicting_ref_values_for_rag() -> None:
    retrieval = {
        "message": "According to the selected Maia sources, when was the term machine learning coined?",
        "snippets": [
            {
                "text": "This source says the term machine learning was coined in 1959 by Arthur Samuel.",
                "page_label": "1",
                "score": 0.9,
                "source_id": "file-1",
                "source_name": "source-a.txt",
                "source_type": "file",
                "credibility_tier": "platform",
            },
            {
                "text": "This source says the term machine learning was coined in 1952 in early computing discussions.",
                "page_label": "1",
                "score": 0.88,
                "source_id": "file-2",
                "source_name": "source-b.txt",
                "source_type": "file",
                "credibility_tier": "platform",
            },
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 2,
        "covered_scope_count": 2,
        "selected_scope_ids": ["file-1", "file-2"],
        "selected_scope_sources": [],
        "all_project_sources": ["source-a.txt", "source-b.txt"],
        "focus_meta": {},
        "evidence_confidence": 0.91,
        "evidence_reason": "Selected Maia sources disagree on the date.",
    }

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: (
            "The first selected source reports 1959 [1]. "
            "The second selected source reports 1952 [2]. "
            "The selected Maia sources therefore disagree on the date."
        ),
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {
            "claims_evaluated": 3,
            "supported_claims": 0,
            "contradicted_claims": 0,
            "mixed_claims": 0,
            "rows": [
                {"claim": "The first selected source reports 1959.", "ref_ids": [1], "status": "insufficient", "support_votes": 0, "contradiction_votes": 0},
                {"claim": "The second selected source reports 1952.", "ref_ids": [2], "status": "insufficient", "support_votes": 0, "contradiction_votes": 0},
            ],
        },
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: None,
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: (
                [
                    {**snippets[0], "ref_id": 1, "ref": "1"},
                    {**snippets[1], "ref_id": 2, "ref": "2"},
                ],
                [
                    {
                        "id": 1,
                        "label": "1",
                        "credibility_tier": "platform",
                        "phrase": "This source says the term machine learning was coined in 1959 by Arthur Samuel.",
                    },
                    {
                        "id": 2,
                        "label": "2",
                        "credibility_tier": "platform",
                        "phrase": "This source says the term machine learning was coined in 1952 in early computing discussions.",
                    },
                ],
            ),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    assert answering["info_panel"]["answer_origin"] == "conflict_aware_grounded_synthesis"
    summary = answering["info_panel"]["evidence_conflict_summary"]
    assert summary["status"] == "contradicted"
    assert summary["rows"][0]["synthetic"] is True
    assert "1952" in summary["rows"][0]["claim"]
    assert "1959" in summary["rows"][0]["claim"]
    assert summary["has_credibility_preference"] is False
    assert "## Conflicting Evidence" in answering["answer"]
    assert "prefer the higher-credibility evidence" not in answering["answer"].lower()
    assert "treat the disputed values as unresolved" in answering["answer"].lower()


def test_build_answer_phase_does_not_infer_conflict_from_single_selected_source() -> None:
    retrieval = {
        "message": "What is this PDF about?",
        "snippets": [
            {
                "text": "Chapter 56 introduces biochemical regulation and metabolic control.",
                "page_label": "56",
                "score": 0.9,
                "source_id": "file-1",
                "file_id": "file-1",
                "source_name": "biochemistry.pdf",
                "source_type": "pdf",
                "credibility_tier": "platform",
            },
            {
                "text": "Page 182 covers thermodynamics and enzyme kinetics in more depth.",
                "page_label": "182",
                "score": 0.88,
                "source_id": "file-1",
                "file_id": "file-1",
                "source_name": "biochemistry.pdf",
                "source_type": "pdf",
                "credibility_tier": "platform",
            },
        ],
        "chat_history": [],
        "primary_source_note": "",
        "requested_language": None,
        "is_follow_up": False,
        "mode_variant": "rag",
        "selected_scope_count": 1,
        "covered_scope_count": 1,
        "selected_scope_ids": ["file-1"],
        "selected_scope_sources": [],
        "all_project_sources": ["biochemistry.pdf"],
        "focus_meta": {},
        "evidence_confidence": 0.82,
        "evidence_reason": "",
    }

    answering = build_answer_phase(
        request=type(
            "Req",
            (),
            {
                "citation": "required",
                "use_mindmap": False,
                "mindmap_settings": {},
                "mindmap_focus": {},
            },
        )(),
        logger=type("L", (), {"warning": staticmethod(lambda *args, **kwargs: None)})(),
        retrieval=retrieval,
        call_openai_fast_qa_fn=lambda **kwargs: "The PDF is a biochemistry textbook covering biochemical regulation, thermodynamics, and enzyme kinetics. [1] [2]",
        normalize_fast_answer_fn=lambda answer, question: answer,
        build_no_relevant_evidence_answer_fn=lambda message, response_language=None: "no evidence",
        resolve_required_citation_mode_fn=lambda value: value,
        render_fast_citation_links_fn=lambda answer, refs, citation_mode: answer,
        build_fast_info_html_fn=lambda snippets_with_refs, max_blocks=12: "<div>info</div>",
        enforce_required_citations_fn=lambda answer, info_html, citation_mode: answer,
        build_source_usage_fn=lambda *args, **kwargs: [],
        build_claim_signal_summary_fn=lambda *args, **kwargs: {
            "claims_evaluated": 2,
            "supported_claims": 0,
            "contradicted_claims": 0,
            "mixed_claims": 0,
            "rows": [
                {"claim": "The PDF discusses biochemical regulation.", "ref_ids": [1], "status": "insufficient", "support_votes": 0, "contradiction_votes": 0},
                {"claim": "The PDF also covers thermodynamics.", "ref_ids": [2], "status": "insufficient", "support_votes": 0, "contradiction_votes": 0},
            ],
        },
        build_citation_quality_metrics_fn=lambda *args, **kwargs: {},
        build_info_panel_copy_fn=lambda *args, **kwargs: {},
        build_knowledge_map_fn=lambda *args, **kwargs: {},
        build_verification_evidence_items_fn=lambda *args, **kwargs: [],
        build_web_review_content_fn=lambda *args, **kwargs: {},
        build_sources_used_fn=lambda *args, **kwargs: [],
        chunk_text_for_stream_fn=None,
        emit_activity_fn=lambda **kwargs: None,
        emit_stream_event_fn=lambda payload: None,
        constants={
            "assign_fast_source_refs_fn": lambda snippets: (
                [
                    {**snippets[0], "ref_id": 1, "ref": "1"},
                    {**snippets[1], "ref_id": 2, "ref": "2"},
                ],
                [
                    {
                        "id": 1,
                        "label": "1",
                        "file_id": "file-1",
                        "source_id": "file-1",
                        "source_name": "biochemistry.pdf",
                        "credibility_tier": "platform",
                        "phrase": "Chapter 56 introduces biochemical regulation and metabolic control.",
                    },
                    {
                        "id": 2,
                        "label": "2",
                        "file_id": "file-1",
                        "source_id": "file-1",
                        "source_name": "biochemistry.pdf",
                        "credibility_tier": "platform",
                        "phrase": "Page 182 covers thermodynamics and enzyme kinetics in more depth.",
                    },
                ],
            ),
            "truncate_for_log_fn": lambda value, limit=1600: str(value),
            "MAIA_SOURCE_USAGE_HEATMAP_ENABLED": True,
            "MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD": 0.8,
            "VERIFICATION_CONTRACT_VERSION": "test",
            "MAIA_CITATION_STRENGTH_ORDERING_ENABLED": True,
        },
    )

    assert answering is not None
    assert answering["info_panel"].get("evidence_conflict_summary") in ({}, None)
    assert answering["info_panel"].get("answer_origin") != "conflict_aware_grounded_synthesis"
    assert "## Conflicting Evidence" not in answering["answer"]
