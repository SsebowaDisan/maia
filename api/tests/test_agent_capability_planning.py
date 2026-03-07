from __future__ import annotations

from unittest.mock import patch

from api.schemas import ChatRequest
from api.services.agent.intelligence_sections.models import TaskIntelligence
from api.services.agent.orchestration.models import TaskPreparation
from api.services.agent.orchestration.step_planner_sections.capability_planning import (
    analyze_capability_plan,
)


class _RegistryStub:
    def __init__(self, tool_ids: list[str]) -> None:
        self._tool_ids = tool_ids

    def list_tools(self) -> list[dict[str, str]]:
        return [{"tool_id": tool_id} for tool_id in self._tool_ids]


def _task_prep(
    *,
    intent_tags: tuple[str, ...],
    contract_actions: list[str],
    contract_objective: str,
) -> TaskPreparation:
    task_intelligence = TaskIntelligence(
        objective=contract_objective,
        target_url="",
        target_host="",
        delivery_email="ops@example.com" if "send_email" in contract_actions else "",
        requires_delivery="send_email" in contract_actions,
        requires_web_inspection=False,
        requested_report="create_document" in contract_actions,
        intent_tags=intent_tags,
    )
    return TaskPreparation(
        task_intelligence=task_intelligence,
        user_preferences={},
        research_depth_profile={},
        conversation_summary="",
        rewritten_task=contract_objective,
        planned_deliverables=[],
        planned_constraints=[],
        task_contract={},
        contract_objective=contract_objective,
        contract_outputs=[],
        contract_facts=[],
        contract_actions=contract_actions,
        contract_target="",
        contract_missing_requirements=[],
        contract_success_checks=[],
        memory_context_snippets=[],
        clarification_blocked=False,
        clarification_questions=[],
    )


def test_capability_analysis_prioritizes_company_agent_workspace_and_email() -> None:
    registry = _RegistryStub(
        [
            "workspace.docs.research_notes",
            "workspace.sheets.track_step",
            "gmail.draft",
            "gmail.send",
            "report.generate",
            "marketing.web_research",
        ]
    )
    request = ChatRequest(
        message="Research this company and send an email summary to ops@example.com",
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=("web_research", "email_delivery"),
        contract_actions=["send_email", "create_document"],
        contract_objective="Research and send summary email",
    )

    analysis = analyze_capability_plan(
        request=request,
        task_prep=prep,
        registry=registry,
    )

    assert "email_ops" in analysis.required_domains
    assert "document_ops" in analysis.required_domains
    assert "workspace.sheets.track_step" in analysis.preferred_tool_ids
    assert "workspace.docs.research_notes" in analysis.preferred_tool_ids


def test_capability_analysis_detects_invoice_domain_from_contract_actions() -> None:
    registry = _RegistryStub(
        [
            "invoice.create",
            "invoice.send",
            "workspace.docs.research_notes",
            "workspace.sheets.track_step",
        ]
    )
    request = ChatRequest(
        message="Create and send invoice INV-2026-001 for this client",
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=(),
        contract_actions=["create_invoice", "send_invoice"],
        contract_objective="Create and send invoice",
    )

    analysis = analyze_capability_plan(
        request=request,
        task_prep=prep,
        registry=registry,
    )

    assert "invoice" in analysis.required_domains
    assert "invoice.create" in analysis.preferred_tool_ids
    assert any(
        signal.startswith("contract_action:create_invoice")
        for signal in analysis.matched_signals
    )


def test_capability_analysis_accepts_business_workflow_domain_from_llm_inference() -> None:
    registry = _RegistryStub(
        [
            "business.ga4_kpi_sheet_report",
            "workspace.docs.research_notes",
            "workspace.sheets.track_step",
        ]
    )
    request = ChatRequest(
        message="Create a weekly GA4 report in sheets for leadership.",
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=(),
        contract_actions=[],
        contract_objective="Weekly GA4 sheet report",
    )

    with patch(
        "api.services.agent.orchestration.step_planner_sections.capability_planning._infer_domains_with_llm",
        return_value=["business_workflow"],
    ):
        analysis = analyze_capability_plan(
            request=request,
            task_prep=prep,
            registry=registry,
        )

    assert "business_workflow" in analysis.required_domains
    assert "business.ga4_kpi_sheet_report" in analysis.preferred_tool_ids
    assert any(signal.startswith("llm_domain:business_workflow") for signal in analysis.matched_signals)


def test_capability_analysis_accepts_google_api_domain_from_llm_inference() -> None:
    registry = _RegistryStub(
        [
            "google.api.google_sheets",
            "workspace.docs.research_notes",
            "workspace.sheets.track_step",
            "report.generate",
        ]
    )
    request = ChatRequest(
        message="Use Google Sheets API to append a KPI tracker row for this campaign.",
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=("sheets_update",),
        contract_actions=["update_sheet"],
        contract_objective="Append KPI tracker row via Google Sheets API",
    )

    with patch(
        "api.services.agent.orchestration.step_planner_sections.capability_planning._infer_domains_with_llm",
        return_value=["document_ops"],
    ):
        analysis = analyze_capability_plan(
            request=request,
            task_prep=prep,
            registry=registry,
        )

    assert "document_ops" in analysis.required_domains
    assert "google.api.google_sheets" in analysis.preferred_tool_ids
    assert any(signal.startswith("llm_domain:document_ops") for signal in analysis.matched_signals)


def test_capability_analysis_accepts_data_science_domain_from_llm_inference() -> None:
    registry = _RegistryStub(
        [
            "data.science.profile",
            "data.science.visualize",
            "data.science.ml.train",
            "report.generate",
        ]
    )
    request = ChatRequest(
        message="Run data science analysis and machine learning on this dataset.",
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=(),
        contract_actions=[],
        contract_objective="Data science modeling workflow",
    )

    with patch(
        "api.services.agent.orchestration.step_planner_sections.capability_planning._infer_domains_with_llm",
        return_value=["data_analysis"],
    ):
        analysis = analyze_capability_plan(
            request=request,
            task_prep=prep,
            registry=registry,
        )

    assert "data_analysis" in analysis.required_domains
    assert "data.science.profile" in analysis.preferred_tool_ids
    assert any(signal.startswith("llm_domain:data_analysis") for signal in analysis.matched_signals)


def test_capability_analysis_does_not_force_workspace_tools_without_workspace_signal() -> None:
    registry = _RegistryStub(
        [
            "marketing.web_research",
            "report.generate",
            "workspace.docs.research_notes",
            "workspace.sheets.track_step",
        ]
    )
    request = ChatRequest(
        message="Research this company and summarize key findings.",
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=("web_research",),
        contract_actions=[],
        contract_objective="Research and summarize key findings",
    )

    analysis = analyze_capability_plan(
        request=request,
        task_prep=prep,
        registry=registry,
    )

    assert "workspace.docs.research_notes" not in analysis.preferred_tool_ids
    assert "workspace.sheets.track_step" not in analysis.preferred_tool_ids


def test_capability_analysis_filters_ungrounded_llm_analytics_domain() -> None:
    registry = _RegistryStub(
        [
            "marketing.web_research",
            "report.generate",
            "gmail.draft",
            "analytics.ga4.report",
            "analytics.chart.generate",
        ]
    )
    request = ChatRequest(
        message='analysis https://axongroup.com/ and send a report to "ops@example.com"',
        agent_mode="company_agent",
    )
    prep = _task_prep(
        intent_tags=("web_research", "report_generation", "email_delivery"),
        contract_actions=["send_email"],
        contract_objective="Analyze website and send report",
    )

    with patch(
        "api.services.agent.orchestration.step_planner_sections.capability_planning._infer_domains_with_llm",
        return_value=["analytics"],
    ):
        analysis = analyze_capability_plan(
            request=request,
            task_prep=prep,
            registry=registry,
        )

    assert "analytics" not in analysis.required_domains
    assert "analytics.ga4.report" not in analysis.preferred_tool_ids
