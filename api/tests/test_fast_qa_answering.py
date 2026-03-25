from api.services.chat.fast_qa_turn_sections.answering import (
    _build_evidence_limited_answer,
    _build_model_failure_answer,
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
