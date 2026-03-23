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
from api.services.agent.orchestration.step_planner_sections.contracts import (
    enforce_contract_synthesis_step,
    insert_contract_probe_steps,
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


def test_workspace_logging_setting_requires_explicit_user_request_by_default() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.company_agent_always_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is False


def test_workspace_logging_ignores_contract_or_intent_without_explicit_message_terms() -> None:
    request = ChatRequest(
        message="Search the web and send an email summary.",
        agent_mode="company_agent",
    )
    task_prep = _task_prep(
        contract_actions=["create_document", "update_sheet"],
        intent_tags=("docs_write", "sheets_update"),
    )
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.company_agent_always_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is False


def test_workspace_logging_can_be_force_enabled_when_explicit_guard_disabled() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={
            "agent.company_agent_always_workspace_logging": True,
            "agent.workspace_logging_require_user_request": False,
        },
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


def test_deep_research_workspace_logging_setting_requires_explicit_user_request_by_default() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={"agent.deep_research_workspace_logging": True},
        task_prep=task_prep,
        deep_research_mode=True,
    )
    assert plan.workspace_logging_requested is False
    assert plan.deep_workspace_logging_enabled is False


def test_deep_research_workspace_logging_setting_can_force_enable_when_guard_disabled() -> None:
    request = ChatRequest(message="what is machine learning", agent_mode="company_agent")
    task_prep = _task_prep(contract_actions=[], intent_tags=())
    plan = build_workspace_logging_plan(
        request=request,
        settings={
            "agent.deep_research_workspace_logging": True,
            "agent.workspace_logging_require_user_request": False,
        },
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


def test_enforce_web_only_research_path_skips_for_ga4_flows() -> None:
    request = ChatRequest(
        message="Create a GA4 report for leadership.",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(tool_id="analytics.ga4.full_report", title="Run full GA4 report", params={}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={}),
    ]
    research_plan = build_research_plan(request=request, settings={})
    constrained = enforce_web_only_research_path(
        request=request,
        settings={"__research_web_only": True},
        steps=steps,
        research_plan=research_plan,
    )
    tool_ids = [step.tool_id for step in constrained]
    assert tool_ids == ["analytics.ga4.full_report", "report.generate"]


def test_enforce_web_only_research_path_respects_allowed_tool_ids() -> None:
    request = ChatRequest(
        message="Research machine learning and send an email summary.",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={}),
    ]
    research_plan = build_research_plan(request=request, settings={})
    constrained = enforce_web_only_research_path(
        request=request,
        settings={"__research_web_only": True},
        steps=steps,
        research_plan=research_plan,
        allowed_tool_ids={"marketing.web_research"},
    )
    assert [step.tool_id for step in constrained] == ["marketing.web_research"]


def test_enforce_contract_synthesis_step_respects_allowed_tool_ids() -> None:
    request = ChatRequest(
        message="Research machine learning and send an email summary.",
        agent_mode="company_agent",
    )
    task_prep = SimpleNamespace(
        contract_outputs=["email summary"],
        task_contract={"required_outputs": ["email summary"]},
        planned_deliverables=["email summary"],
        contract_objective="Research machine learning and prepare an email summary.",
        rewritten_task=request.message,
        contract_facts=["Key findings with citations."],
    )
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search online sources",
            params={"query": "machine learning"},
        ),
        PlannedStep(
            tool_id="gmail.draft",
            title="Draft email",
            params={"to": "ssebowadisan1@gmail.com"},
        ),
    ]
    constrained = enforce_contract_synthesis_step(
        request=request,
        task_prep=task_prep,
        steps=steps,
        allowed_tool_ids={"marketing.web_research", "gmail.draft"},
    )
    assert [step.tool_id for step in constrained] == ["marketing.web_research", "gmail.draft"]


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


def test_insert_contract_probe_steps_filters_non_web_probe_tools_for_target_url(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import contracts as contracts_module

    monkeypatch.setattr(
        contracts_module,
        "propose_fact_probe_steps",
        lambda **kwargs: [
            {
                "tool_id": "analytics.ga4.report",
                "title": "Gather site performance metrics",
                "params": {"url": "https://axongroup.com/"},
            },
            {
                "tool_id": "browser.playwright.inspect",
                "title": "Collect missing evidence",
                "params": {"url": "https://axongroup.com/products-and-solutions"},
            },
        ],
    )
    request = ChatRequest(
        message='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        agent_mode="company_agent",
    )
    task_prep = SimpleNamespace(
        task_contract={"required_facts": ["core findings"]},
        task_intelligence=SimpleNamespace(target_url="https://axongroup.com/"),
    )
    steps = [
        PlannedStep(
            tool_id="browser.playwright.inspect",
            title="Inspect website",
            params={"url": "https://axongroup.com/"},
        ),
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": request.message},
        ),
    ]
    result = insert_contract_probe_steps(
        request=request,
        task_prep=task_prep,
        steps=steps,
        allowed_tool_ids=["analytics.ga4.report", "browser.playwright.inspect"],
    )
    tool_ids = [step.tool_id for step in result]
    assert "analytics.ga4.report" not in tool_ids
    assert tool_ids.count("browser.playwright.inspect") == 2


def test_insert_contract_probe_steps_filters_web_probe_for_ga4_context(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import contracts as contracts_module

    monkeypatch.setattr(
        contracts_module,
        "propose_fact_probe_steps",
        lambda **kwargs: [
            {
                "tool_id": "marketing.web_research",
                "title": "Collect evidence for required facts",
                "params": {"query": "Google Analytics report generation"},
            },
            {
                "tool_id": "analytics.ga4.full_report",
                "title": "Collect analytics evidence",
                "params": {},
            },
        ],
    )
    request = ChatRequest(
        message="Analyze Google Analytics property 479179141 and make a report.",
        agent_mode="company_agent",
    )
    task_prep = SimpleNamespace(
        task_contract={"required_facts": ["Include specific metrics in the report."]},
        task_intelligence=SimpleNamespace(target_url=""),
        contract_objective="Google Analytics report",
    )
    steps = [
        PlannedStep(
            tool_id="analytics.ga4.report",
            title="Generate GA4 report",
            params={},
        ),
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": request.message},
        ),
    ]
    result = insert_contract_probe_steps(
        request=request,
        task_prep=task_prep,
        steps=steps,
        allowed_tool_ids=["marketing.web_research", "analytics.ga4.full_report"],
    )
    tool_ids = [step.tool_id for step in result]
    assert "marketing.web_research" not in tool_ids
    assert tool_ids.count("analytics.ga4.full_report") == 1


def test_insert_contract_probe_steps_skips_document_highlight_without_file_scope(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import contracts as contracts_module

    monkeypatch.setattr(
        contracts_module,
        "propose_fact_probe_steps",
        lambda **kwargs: [
            {
                "tool_id": "documents.highlight.extract",
                "title": "Extract key insights and attributions from inspected pages",
                "params": {"sources": ["stanford.ai.index.report"]},
            },
            {
                "tool_id": "marketing.web_research",
                "title": "Collect missing evidence",
                "params": {"query": "machine learning overview"},
            },
        ],
    )
    request = ChatRequest(
        message="Research machine learning online and email a summary.",
        agent_mode="company_agent",
    )
    task_prep = SimpleNamespace(
        task_contract={"required_facts": ["balanced machine learning overview"]},
        task_intelligence=SimpleNamespace(target_url=""),
    )
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="Search online sources",
            params={"query": request.message},
        ),
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": request.message},
        ),
    ]
    result = insert_contract_probe_steps(
        request=request,
        task_prep=task_prep,
        steps=steps,
        allowed_tool_ids=["documents.highlight.extract", "marketing.web_research"],
    )
    tool_ids = [step.tool_id for step in result]
    assert "documents.highlight.extract" not in tool_ids


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
    task_prep = _task_prep(contract_actions=["submit_contact_form"], intent_tags=("web_research",))
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
        settings={"__contact_form_capability_enabled": True},
        task_prep=task_prep,
        steps=steps,
    )
    tool_ids = [step.tool_id for step in enriched]
    assert "browser.contact_form.send" in tool_ids
    contact_step = next(step for step in enriched if step.tool_id == "browser.contact_form.send")
    assert contact_step.params.get("url") == "https://axongroup.com/"


def test_intent_enrichment_skips_contact_form_when_specialist_capability_disabled(monkeypatch) -> None:
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
        message="Analyze and contact them through the website form.",
        agent_mode="company_agent",
    )
    task_prep = _task_prep(contract_actions=["submit_contact_form"], intent_tags=("contact_form_submission",))
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
        settings={"__contact_form_capability_enabled": False},
        task_prep=task_prep,
        steps=steps,
    )
    assert all(step.tool_id != "browser.contact_form.send" for step in enriched)


def test_intent_enrichment_does_not_use_heuristic_phrase_only_for_contact_step(monkeypatch) -> None:
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
        message="Please contact them.",
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
        settings={"__contact_form_capability_enabled": True},
        task_prep=task_prep,
        steps=steps,
    )
    assert all(step.tool_id != "browser.contact_form.send" for step in enriched)


def test_intent_enrichment_can_use_contract_planning_signals_for_contact_step(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    monkeypatch.setattr(
        enrichment_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {
            "url": "https://axongroup.com/",
            "wants_contact_form": False,
            "wants_highlight_words": False,
            "wants_docs_output": False,
            "wants_sheets_output": False,
        },
    )
    request = ChatRequest(
        message="Analyze the site and proceed with approved outreach workflow.",
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
        settings={
            "__contact_form_capability_enabled": True,
            "__capability_required_domains": ["outreach"],
            "__capability_preferred_tool_ids": ["browser.contact_form.send"],
        },
        task_prep=task_prep,
        steps=steps,
    )
    assert any(step.tool_id == "browser.contact_form.send" for step in enriched)


def test_intent_enrichment_research_only_prunes_delivery_and_workspace_steps(monkeypatch) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    def _fake_signals(**kwargs):
        agent_goal = " ".join(str(kwargs.get("agent_goal") or "").split()).strip()
        if agent_goal:
            return {
                "url": "https://axongroup.com/",
                "wants_contact_form": True,
                "wants_highlight_words": False,
                "wants_docs_output": True,
                "wants_sheets_output": True,
            }
        return {
            "url": "https://axongroup.com/",
            "wants_contact_form": False,
            "wants_highlight_words": False,
            "wants_docs_output": False,
            "wants_sheets_output": False,
        }

    monkeypatch.setattr(enrichment_module, "infer_intent_signals_from_text", _fake_signals)
    request = ChatRequest(
        message="Deep research machine learning trends from web sources.",
        agent_mode="deep_search",
        agent_goal="Conversation context: send to stale@example.com and update docs",
    )
    task_prep = _task_prep(
        contract_actions=["create_document", "update_sheet", "submit_contact_form"],
        intent_tags=("docs_write", "sheets_update", "contact_form_submission"),
    )
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search online sources", params={"query": "x"}),
        PlannedStep(tool_id="workspace.docs.research_notes", title="Write notes", params={}),
        PlannedStep(tool_id="workspace.sheets.track_step", title="Track step", params={}),
        PlannedStep(tool_id="gmail.send", title="Send email", params={"to": "stale@example.com"}),
        PlannedStep(tool_id="browser.contact_form.send", title="Send outreach", params={"url": "https://axongroup.com/"}),
        PlannedStep(tool_id="report.generate", title="Generate report", params={"summary": "x"}),
    ]

    enriched = apply_intent_enrichment(
        request=request,
        settings={"__deep_search_enabled": True, "__contact_form_capability_enabled": True},
        task_prep=task_prep,
        steps=steps,
    )

    tool_ids = [step.tool_id for step in enriched]
    assert "marketing.web_research" in tool_ids
    assert "report.generate" in tool_ids
    assert "workspace.docs.research_notes" not in tool_ids
    assert "workspace.sheets.track_step" not in tool_ids
    assert "gmail.send" not in tool_ids
    assert "browser.contact_form.send" not in tool_ids


def test_intent_enrichment_prunes_workspace_steps_without_explicit_request(
    monkeypatch,
) -> None:
    from api.services.agent.orchestration.step_planner_sections import intent_enrichment as enrichment_module

    # Simulate noisy inferred signals; explicit message should still control
    # Docs/Sheets inclusion when the explicit guard is enabled.
    monkeypatch.setattr(
        enrichment_module,
        "infer_intent_signals_from_text",
        lambda **kwargs: {
            "url": "https://axongroup.com/",
            "wants_contact_form": False,
            "wants_highlight_words": False,
            "wants_docs_output": True,
            "wants_sheets_output": True,
        },
    )
    request = ChatRequest(
        message="Search axongroup.com and send an email summary.",
        agent_mode="company_agent",
    )
    task_prep = _task_prep(
        contract_actions=["create_document", "update_sheet"],
        intent_tags=("docs_write", "sheets_update"),
    )
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Search web", params={"query": "axon group"}),
        PlannedStep(tool_id="workspace.docs.research_notes", title="Write notes", params={}),
        PlannedStep(tool_id="workspace.sheets.track_step", title="Track step", params={}),
        PlannedStep(tool_id="gmail.send", title="Send email", params={"to": "person@example.com"}),
    ]

    enriched = apply_intent_enrichment(
        request=request,
        settings={"agent.workspace_logging_require_user_request": True},
        task_prep=task_prep,
        steps=steps,
    )
    tool_ids = [step.tool_id for step in enriched]
    assert "marketing.web_research" in tool_ids
    assert "gmail.send" in tool_ids
    assert "workspace.docs.research_notes" not in tool_ids
    assert "workspace.sheets.track_step" not in tool_ids


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
