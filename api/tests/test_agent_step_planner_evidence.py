from types import SimpleNamespace

from api.schemas import ChatRequest
from api.services.agent.orchestration.step_planner_sections.evidence import (
    enforce_evidence_path,
    summarize_fact_coverage,
)
from api.services.agent.planner import PlannedStep


def _task_prep(*, contract_facts: list[str], target_url: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        contract_facts=contract_facts,
        task_intelligence=SimpleNamespace(target_url=target_url),
    )


def test_summarize_fact_coverage_reports_missing_facts() -> None:
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="General company research",
            params={"query": "company overview"},
        )
    ]
    summary = summarize_fact_coverage(
        contract_facts=["Headquarters city and country", "Primary services offered"],
        steps=steps,
    )
    assert summary["required_fact_count"] == 2
    assert summary["covered_fact_count"] == 0
    assert len(summary["missing_facts"]) == 2


def test_enforce_evidence_path_regenerates_step_for_uncovered_facts() -> None:
    request = ChatRequest(
        message="Analyze the company",
        agent_mode="company_agent",
    )
    steps = [
        PlannedStep(
            tool_id="marketing.web_research",
            title="General company research",
            params={"query": "company overview"},
        ),
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": "Company analysis"},
        ),
    ]
    prepared = _task_prep(
        contract_facts=["Headquarters city and country"],
        target_url="https://example.com",
    )
    planned = enforce_evidence_path(
        request=request,
        task_prep=prepared,  # type: ignore[arg-type]
        steps=steps,
        highlight_color="yellow",
    )
    remediation_step = next(
        (
            step
            for step in planned
            if step.title == "Collect missing evidence for uncovered required facts"
        ),
        None,
    )
    assert remediation_step is not None
    assert remediation_step.tool_id == "browser.playwright.inspect"
    assert "Headquarters city and country" in remediation_step.expected_evidence
    summary = summarize_fact_coverage(
        contract_facts=["Headquarters city and country"],
        steps=planned,
    )
    assert summary["covered_fact_count"] == 1
    assert summary["missing_facts"] == []
