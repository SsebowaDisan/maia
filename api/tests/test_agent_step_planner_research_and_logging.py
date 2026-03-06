from __future__ import annotations

from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration.step_planner_sections import research as research_module
from api.services.agent.orchestration.step_planner_sections.research import (
    build_research_plan,
    enforce_deep_file_scope_policy,
    enforce_web_only_research_path,
    ensure_company_agent_highlight_step,
    normalize_step_parameters,
)
from api.services.agent.orchestration.step_planner_sections.intent_enrichment import (
    apply_intent_enrichment,
)
from api.services.agent.orchestration.step_planner_sections.workspace_logging import (
    build_workspace_logging_plan,
    prepend_workspace_roadmap_steps,
)
from api.services.agent.planner import PlannedStep


def _task_prep(*, contract_actions: list[str], intent_tags: tuple[str, ...]):
    return SimpleNamespace(
        contract_actions=contract_actions,
        task_intelligence=SimpleNamespace(intent_tags=intent_tags),
    )


def test_workspace_logging_disabled_by_default_for_company_agent_mode() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is False


def test_workspace_logging_can_be_enabled_for_company_agent_mode_via_setting() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.company_agent_always_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is True


def test_workspace_logging_enabled_when_update_sheet_requested() -> None:
    request = ChatRequest(message="update this in sheets", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=["update_sheet"], intent_tags=("sheets_update",))
    plan = build_workspace_logging_plan(
        request=request,
        settings={},
        task_prep=task_prep,
        deep_research_mode=False,
    )
    assert plan.workspace_logging_requested is True
    assert plan.deep_workspace_logging_enabled is True


def test_workspace_logging_can_be_enabled_for_deep_research_via_setting() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.deep_research_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is True


def test_company_agent_highlight_step_not_inserted_without_signal(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {"wants_highlight_words": False, "wants_file_scope": False},
    )
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    steps = [
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": "what is machine learning"},
        )
    ]
    result = ensure_company_agent_highlight_step(
        request=request,
        settings={},
        steps=steps,
        highlight_color="yellow",
        planned_keywords=["machine", "learning"],
    )
    assert all(step.tool_id != "documents.highlight.extract" for step in result)


def test_company_agent_highlight_step_inserted_when_user_requests_highlighting(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {"wants_highlight_words": True, "wants_file_scope": False},
    )
    request = ChatRequest(
        message="highlight copied words from these files and summarize",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": "highlight copied words"},
        )
    ]
    result = ensure_company_agent_highlight_step(
        request=request,
        settings={},
        steps=steps,
        highlight_color="green",
        planned_keywords=["highlight", "copied words"],
    )
    assert any(step.tool_id == "documents.highlight.extract" for step in result)


def test_company_agent_highlight_step_not_inserted_for_generic_deep_search_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {"wants_highlight_words": False, "wants_file_scope": True},
    )
    request = ChatRequest(
        message="Deep research machine learning trends online.",
        agent_mode="company_agent",
        index_selection={"1": {"mode": "select", "file_ids": ["auto-a", "auto-b"]}},
    )
    steps = [PlannedStep(tool_id="report.generate", title="Generate report", params={})]
    result = ensure_company_agent_highlight_step(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": False,
            "__deep_search_user_selected_files": False,
        },
        steps=steps,
        highlight_color="yellow",
        planned_keywords=["machine", "learning"],
    )
    assert all(step.tool_id != "documents.highlight.extract" for step in result)


def test_company_agent_highlight_step_inserted_for_prompt_scoped_pdfs(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {"wants_highlight_words": False, "wants_file_scope": True},
    )
    request = ChatRequest(
        message="Deep research the Alpha group PDFs.",
        agent_mode="company_agent",
    )
    steps = [PlannedStep(tool_id="report.generate", title="Generate report", params={})]
    result = ensure_company_agent_highlight_step(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": True,
            "__deep_search_user_selected_files": False,
        },
        steps=steps,
        highlight_color="yellow",
        planned_keywords=["alpha", "pdf"],
    )
    assert any(step.tool_id == "documents.highlight.extract" for step in result)


def test_company_agent_highlight_step_not_inserted_for_deep_mode_without_file_scope(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        research_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {"wants_highlight_words": True, "wants_file_scope": False},
    )
    request = ChatRequest(
        message="Deep research machine learning trends online.",
        agent_mode="company_agent",
    )
    steps = [PlannedStep(tool_id="report.generate", title="Generate report", params={})]
    result = ensure_company_agent_highlight_step(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": False,
            "__deep_search_user_selected_files": False,
        },
        steps=steps,
        highlight_color="yellow",
        planned_keywords=["machine", "learning"],
    )
    assert all(step.tool_id != "documents.highlight.extract" for step in result)


def test_enforce_deep_file_scope_policy_removes_highlight_without_scope() -> None:
    request = ChatRequest(
        message="Deep research machine learning trends online.",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Web search", params={}),
        PlannedStep(tool_id="documents.highlight.extract", title="Highlight words", params={}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={}),
    ]
    filtered = enforce_deep_file_scope_policy(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": False,
            "__deep_search_user_selected_files": False,
        },
        steps=steps,
    )
    assert [step.tool_id for step in filtered] == ["marketing.web_research", "report.generate"]


def test_enforce_deep_file_scope_policy_keeps_highlight_with_explicit_scope() -> None:
    request = ChatRequest(
        message="Deep research Alpha group PDFs.",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Web search", params={}),
        PlannedStep(tool_id="documents.highlight.extract", title="Highlight words", params={}),
    ]
    filtered = enforce_deep_file_scope_policy(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": True,
            "__deep_search_user_selected_files": False,
        },
        steps=steps,
    )
    assert any(step.tool_id == "documents.highlight.extract" for step in filtered)


def test_build_research_plan_uses_default_keyword_floor(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def _fake_build_research_blueprint(
        *,
        message: str,
        agent_goal: str | None,
        min_keywords: int,
        min_search_terms: int = 4,
        llm_only: bool = True,
        llm_strict: bool = False,
    ):
        del message, agent_goal
        assert llm_only is True
        assert llm_strict is False
        captured["min_keywords"] = min_keywords
        captured["min_search_terms"] = min_search_terms
        return {"search_terms": ["what is machine learning"], "keywords": ["machine", "learning"]}

    monkeypatch.setattr(
        research_module,
        "build_research_blueprint",
        _fake_build_research_blueprint,
    )
    _ = build_research_plan(
        request=ChatRequest(message="what is machine learning", agent_mode="company_agent"),
        settings={},
    )
    assert captured["min_keywords"] == 10
    assert captured["min_search_terms"] >= 4


def test_intent_enrichment_adds_docs_and_sheets_steps_from_llm_signal_when_tags_missing(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    monkeypatch.setattr(
        enrichment_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {
            "wants_highlight_words": False,
            "wants_docs_output": True,
            "wants_sheets_output": True,
        },
    )
    request = ChatRequest(
        message=(
            "Research online competitors, write findings in Google Docs, and track each task in Google Sheets."
        ),
        agent_mode="company_agent",
    )
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={"query": "x"}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]
    enriched = apply_intent_enrichment(
        request=request,
        settings={},
        task_prep=task_prep,
        steps=steps,
    )
    tool_ids = [step.tool_id for step in enriched]
    assert "workspace.docs.research_notes" in tool_ids
    assert "workspace.sheets.track_step" in tool_ids
    assert tool_ids[0] == "workspace.sheets.track_step"


def test_intent_enrichment_skips_deep_highlight_without_explicit_file_scope(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    monkeypatch.setattr(
        enrichment_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {
            "wants_highlight_words": True,
            "wants_file_scope": False,
            "wants_docs_output": False,
            "wants_sheets_output": False,
        },
    )
    request = ChatRequest(
        message="Deep research machine learning trends online.",
        agent_mode="company_agent",
    )
    task_prep = _task_prep(contract_actions=[], intent_tags=("highlight_extract",))
    steps = [PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"})]
    enriched = apply_intent_enrichment(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": False,
            "__deep_search_user_selected_files": False,
        },
        task_prep=task_prep,
        steps=steps,
    )
    assert all(step.tool_id != "documents.highlight.extract" for step in enriched)


def test_intent_enrichment_inserts_deep_highlight_for_prompt_scoped_pdfs(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    monkeypatch.setattr(
        enrichment_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {
            "wants_highlight_words": False,
            "wants_file_scope": False,
            "wants_docs_output": False,
            "wants_sheets_output": False,
        },
    )
    request = ChatRequest(
        message="Deep research Alpha group PDFs.",
        agent_mode="company_agent",
    )
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    steps = [PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"})]
    enriched = apply_intent_enrichment(
        request=request,
        settings={
            "__deep_search_enabled": True,
            "__deep_search_prompt_scoped_pdfs": True,
            "__deep_search_user_selected_files": False,
        },
        task_prep=task_prep,
        steps=steps,
    )
    assert any(step.tool_id == "documents.highlight.extract" for step in enriched)


def test_intent_enrichment_adds_contact_form_step_when_requested(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    monkeypatch.setattr(
        enrichment_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {
            "url": "https://axongroup.com/",
            "wants_contact_form": True,
            "wants_highlight_words": False,
            "wants_docs_output": False,
            "wants_sheets_output": False,
        },
    )
    request = ChatRequest(
        message="Analyze the website and send them a message about their services.",
        agent_mode="company_agent",
    )
    task_prep = _task_prep(contract_actions=[], intent_tags=("web_research",))
    steps = [
        PlannedStep(
            tool_id="browser.playwright.inspect",
            title="Inspect website",
            params={"url": "https://axongroup.com/"},
        ),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]
    enriched = apply_intent_enrichment(
        request=request,
        settings={},
        task_prep=task_prep,
        steps=steps,
    )
    tool_ids = [step.tool_id for step in enriched]
    assert "browser.contact_form.send" in tool_ids
    contact_step = next(step for step in enriched if step.tool_id == "browser.contact_form.send")
    assert contact_step.params.get("url") == "https://axongroup.com/"


def test_workspace_roadmap_steps_marked_for_optional_skip() -> None:
    request = ChatRequest(message="Research online", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={"query": "x"}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]
    with_roadmap = prepend_workspace_roadmap_steps(
        request=request,
        task_prep=task_prep,
        steps=steps,
        planned_search_terms=["research online"],
        planned_keywords=["research", "online"],
    )
    roadmap_only = [step for step in with_roadmap if step.tool_id == "workspace.sheets.track_step"]
    assert roadmap_only
    assert all(bool(step.params.get("__workspace_logging_step")) for step in roadmap_only)


def test_deep_file_budgets_flow_into_highlight_step_params(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "build_research_blueprint",
        lambda **kwargs: {"search_terms": ["energy report"], "keywords": ["energy", "market"]},
    )
    plan = build_research_plan(
        request=ChatRequest(message="Deep research across available PDFs.", agent_mode="company_agent"),
        settings={
            "__research_depth_tier": "deep_research",
            "__file_research_max_sources": 180,
            "__file_research_max_chunks": 1000,
            "__file_research_max_scan_pages": 120,
        },
    )
    steps = [
        PlannedStep(
            tool_id="documents.highlight.extract",
            title="Highlight words in selected files",
            params={},
        )
    ]
    normalized = normalize_step_parameters(
        steps=steps,
        planned_search_terms=plan.planned_search_terms,
        planned_keywords=plan.planned_keywords,
        highlight_color=plan.highlight_color,
        research_plan=plan,
    )
    params = normalized[0].params
    assert int(params.get("max_sources") or 0) == 180
    assert int(params.get("max_chunks") or 0) == 1000
    assert int(params.get("max_scan_pages") or 0) == 120


def test_research_plan_propagates_web_search_budget_to_web_step(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "build_research_blueprint",
        lambda **kwargs: {"search_terms": ["energy market research"], "keywords": ["energy", "market"]},
    )
    plan = build_research_plan(
        request=ChatRequest(message="Run deep search on energy markets.", agent_mode="company_agent"),
        settings={
            "__research_depth_tier": "deep_research",
            "__research_web_search_budget": 350,
            "__research_max_query_variants": 14,
            "__research_results_per_query": 25,
        },
    )
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search online sources",
            params={},
        )
    ]
    normalized = normalize_step_parameters(
        steps=steps,
        planned_search_terms=plan.planned_search_terms,
        planned_keywords=plan.planned_keywords,
        highlight_color=plan.highlight_color,
        research_plan=plan,
    )
    params = normalized[0].params
    assert int(params.get("search_budget") or 0) == 350


def test_web_only_research_path_inserts_web_research_step_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "build_research_blueprint",
        lambda **kwargs: {"search_terms": ["energy policy trends"], "keywords": ["energy", "policy"]},
    )
    request = ChatRequest(message="Research energy policy online.", agent_mode="deep_search")
    plan = build_research_plan(request=request, settings={"__research_web_search_budget": 200})
    steps = [
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "energy"})
    ]
    constrained = enforce_web_only_research_path(
        request=request,
        settings={"__research_web_only": True},
        steps=steps,
        research_plan=plan,
    )
    assert constrained[0].tool_id == "marketing.web_research"
    assert any(step.tool_id == "report.generate" for step in constrained)


def test_web_only_research_path_drops_document_highlight_steps(monkeypatch) -> None:
    monkeypatch.setattr(
        research_module,
        "build_research_blueprint",
        lambda **kwargs: {"search_terms": ["climate energy mix"], "keywords": ["climate", "energy"]},
    )
    request = ChatRequest(message="Deep web search on climate energy mix.", agent_mode="deep_search")
    plan = build_research_plan(request=request, settings={"__research_web_search_budget": 200})
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={"query": "x"}),
        PlannedStep(tool_id="documents.highlight.extract", title="Highlight words", params={}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]
    constrained = enforce_web_only_research_path(
        request=request,
        settings={"__research_web_only": "true"},
        steps=steps,
        research_plan=plan,
    )
    assert all(step.tool_id != "documents.highlight.extract" for step in constrained)
