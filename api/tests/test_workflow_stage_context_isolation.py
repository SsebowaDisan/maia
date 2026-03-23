from __future__ import annotations

from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration import task_preparation as module


def _drain_preparation(gen):
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value


def test_prepare_task_context_skips_session_and_memory_for_explicit_workflow_stage(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "derive_task_intelligence",
        lambda **kwargs: SimpleNamespace(
            objective="Research machine learning sources",
            requires_delivery=False,
            requires_web_inspection=False,
            target_url="",
            intent_tags=(),
            preferred_tone="executive",
            preferred_format="brief",
            to_dict=lambda: {"objective": "Research machine learning sources"},
        ),
    )
    monkeypatch.setattr(module, "infer_user_preferences", lambda **kwargs: {})
    monkeypatch.setattr(module, "get_user_preference_store", lambda: SimpleNamespace(get=lambda **kwargs: {}, merge=lambda **kwargs: {}))
    monkeypatch.setattr(
        module,
        "derive_research_depth_profile",
        lambda **kwargs: SimpleNamespace(
            tier="standard",
            max_query_variants=4,
            results_per_query=6,
            fused_top_k=12,
            max_live_inspections=2,
            min_unique_sources=4,
            source_budget_min=4,
            source_budget_max=8,
            max_search_rounds=1,
            min_keywords=4,
            file_source_budget_min=4,
            file_source_budget_max=8,
            max_file_sources=4,
            max_file_chunks=16,
            max_file_scan_pages=8,
            simple_explanation_required=False,
            include_execution_why=False,
            as_dict=lambda: {"tier": "standard"},
        ),
    )
    monkeypatch.setattr(module, "run_preflight_checks", lambda **kwargs: [])
    monkeypatch.setattr(
        module,
        "rewrite_task_for_execution",
        lambda **kwargs: {"detailed_task": kwargs["message"], "deliverables": [], "constraints": []},
    )
    monkeypatch.setattr(
        module,
        "build_task_contract",
        lambda **kwargs: {
            "objective": "Research machine learning sources",
            "required_outputs": ["cited source list"],
            "required_facts": [],
            "required_actions": [],
            "missing_requirements": [],
            "success_checks": ["sources are relevant"],
            "delivery_target": "",
        },
    )
    monkeypatch.setattr(module, "classify_missing_requirement_slots", lambda **kwargs: [])
    monkeypatch.setattr(module, "with_slot_lifecycle_defaults", lambda slots: slots)
    monkeypatch.setattr(module, "blocking_requirements_from_slots", lambda **kwargs: [])
    monkeypatch.setattr(module, "clarification_questions_from_slots", lambda **kwargs: [])
    monkeypatch.setattr(module, "compile_working_context", lambda seed: {"preview": seed.get("message", ""), "version": "test", "sections": {}})

    session_calls: list[str] = []
    memory_calls: list[str] = []
    monkeypatch.setattr(
        module,
        "get_session_store",
        lambda: SimpleNamespace(
            retrieve_context_snippets=lambda **kwargs: session_calls.append(kwargs["query"]) or ["stale session snippet"]
        ),
    )
    monkeypatch.setattr(
        module,
        "get_memory_service",
        lambda: SimpleNamespace(
            retrieve_context_snippets=lambda **kwargs: memory_calls.append(kwargs["query"]) or ["stale memory snippet"]
        ),
    )

    request = ChatRequest(message="Research machine learning and collect cited sources", agent_mode="company_agent")
    settings = {"__allowed_tool_ids": ["marketing.web_research"]}
    emitted_events: list[str] = []

    prep = _drain_preparation(
        module.prepare_task_context(
            run_id="run_1",
            conversation_id="conv_1",
            user_id="tenant_1",
            request=request,
            settings=settings,
            emit_event=lambda event: emitted_events.append(event.event_type) or {"event_type": event.event_type},
            activity_event_factory=lambda **kwargs: SimpleNamespace(
                event_type=kwargs["event_type"],
                title=kwargs["title"],
                detail=kwargs.get("detail", ""),
                metadata=kwargs.get("metadata", {}),
            ),
        )
    )

    assert session_calls == []
    assert memory_calls == []
    assert prep.session_context_snippets == []
    assert prep.memory_context_snippets == []
    assert "llm.context_session" not in emitted_events
    assert "llm.context_memory" not in emitted_events
