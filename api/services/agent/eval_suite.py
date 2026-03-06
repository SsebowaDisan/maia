from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from api.services.agent.intelligence_sections.contradictions import (
    detect_potential_contradictions,
)
from api.services.agent.intelligence_sections.models import TaskIntelligence
from api.services.agent.intelligence_sections.verification import build_verification_report
from api.services.agent.llm_contracts import (
    build_task_contract,
    verify_task_contract_fulfillment,
)
from api.services.agent.orchestration.step_planner_sections.evidence import (
    enforce_evidence_path,
    summarize_fact_coverage,
)
from api.services.agent.planner import PlannedStep
from api.services.agent.research_depth_profile import derive_research_depth_profile

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "agent_eval_cases.json"
EVAL_THRESHOLDS = {
    "overall_pass_rate": 0.9,
    "ambiguity": 1.0,
    "multi_intent": 1.0,
    "delivery_completeness": 1.0,
    "contradiction_risk": 1.0,
    "depth_routing": 1.0,
    "citation_quality": 1.0,
}


@contextmanager
def _temporary_env(values: dict[str, str]) -> Any:
    previous: dict[str, str | None] = {
        key: os.environ.get(key) for key in values
    }
    try:
        for key, value in values.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_eval_fixtures() -> list[dict[str, str]]:
    if not FIXTURE_PATH.exists():
        return []
    try:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, str]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        case_id = " ".join(str(row.get("id") or "").split()).strip()
        category = " ".join(str(row.get("category") or "").split()).strip()
        description = " ".join(str(row.get("description") or "").split()).strip()
        if not case_id or not category:
            continue
        rows.append(
            {
                "id": case_id,
                "category": category,
                "description": description,
            }
        )
    return rows


def _evaluate_case_ambiguity_missing_requirements() -> dict[str, Any]:
    with _temporary_env({"MAIA_AGENT_LLM_TASK_CONTRACT_ENABLED": "0"}):
        contract = build_task_contract(
            message="Please prepare and send the report.",
            rewritten_task="Prepare and send report",
            deliverables=[],
            constraints=[],
            intent_tags=["email_delivery", "report_generation"],
        )
    missing = contract.get("missing_requirements", [])
    missing_rows = [str(item).strip() for item in missing if str(item).strip()] if isinstance(missing, list) else []
    passed = bool(missing_rows) and "Recipient email address for delivery" in missing_rows
    return {
        "id": "ambiguity_missing_requirements",
        "category": "ambiguity",
        "passed": passed,
        "detail": "; ".join(missing_rows[:4]),
    }


def _evaluate_case_multi_intent_fact_coverage() -> dict[str, Any]:
    request = SimpleNamespace(message="Analyze the company and deliver findings.")
    steps = [
        PlannedStep(
            tool_id="report.generate",
            title="Generate report",
            params={"summary": "Company analysis"},
        )
    ]
    task_prep = SimpleNamespace(
        contract_facts=["Headquarters city and country"],
        task_intelligence=SimpleNamespace(target_url="https://example.com"),
    )
    planned = enforce_evidence_path(
        request=request,
        task_prep=task_prep,  # type: ignore[arg-type]
        steps=steps,
        highlight_color="yellow",
    )
    coverage = summarize_fact_coverage(
        contract_facts=["Headquarters city and country"],
        steps=planned,
    )
    passed = bool(coverage.get("required_fact_count") == 1 and coverage.get("covered_fact_count") == 1)
    return {
        "id": "multi_intent_fact_coverage",
        "category": "multi_intent",
        "passed": passed,
        "detail": f"coverage={coverage}",
    }


def _evaluate_case_external_action_block_unverified_facts() -> dict[str, Any]:
    with _temporary_env({"MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED": "0"}):
        check = verify_task_contract_fulfillment(
            contract={
                "objective": "Find headquarters and send summary",
                "required_facts": ["Headquarters city and country"],
                "required_actions": ["send_email"],
                "delivery_target": "ops@example.com",
            },
            request_message="Analyze and send summary",
            executed_steps=[
                {
                    "tool_id": "marketing.web_research",
                    "status": "success",
                    "summary": "Collected generic company profile.",
                }
            ],
            actions=[],
            report_body="General profile without explicit headquarters fact.",
            sources=[{"url": "https://example.com", "label": "Example", "metadata": {}}],
            allowed_tool_ids=["marketing.web_research", "browser.playwright.inspect", "gmail.draft"],
        )
    missing = check.get("missing_items", [])
    missing_rows = [str(item).strip() for item in missing if str(item).strip()] if isinstance(missing, list) else []
    passed = (
        not bool(check.get("ready_for_external_actions"))
        and any("Unverified required fact" in item for item in missing_rows)
    )
    return {
        "id": "external_action_block_unverified_facts",
        "category": "delivery_completeness",
        "passed": passed,
        "detail": "; ".join(missing_rows[:4]),
    }


def _evaluate_case_delivery_ready_when_contract_satisfied() -> dict[str, Any]:
    with _temporary_env({"MAIA_AGENT_LLM_DELIVERY_CHECK_ENABLED": "0"}):
        check = verify_task_contract_fulfillment(
            contract={
                "objective": "Find headquarters and send summary",
                "required_facts": ["Headquarters city and country"],
                "required_actions": ["send_email"],
                "delivery_target": "ops@example.com",
            },
            request_message="Analyze and send summary",
            executed_steps=[
                {
                    "tool_id": "browser.playwright.inspect",
                    "status": "success",
                    "summary": "Headquarters city and country confirmed from source evidence.",
                }
            ],
            actions=[{"tool_id": "gmail.send", "status": "success", "summary": "Email sent to ops@example.com"}],
            report_body="Required fact confirmed: Headquarters city and country.",
            sources=[{"url": "https://example.com/about", "label": "About page", "metadata": {}}],
            allowed_tool_ids=["gmail.draft", "gmail.send", "browser.playwright.inspect"],
        )
    passed = bool(check.get("ready_for_final_response")) and bool(check.get("ready_for_external_actions"))
    return {
        "id": "delivery_ready_when_contract_satisfied",
        "category": "delivery_completeness",
        "passed": passed,
        "detail": str(check),
    }


def _evaluate_case_contradiction_risk_signal() -> dict[str, Any]:
    contradictions = detect_potential_contradictions(
        [
            {
                "source": "Source A",
                "url": "https://example.com/a",
                "text": "Axon Group has 100 employees and 6 locations in Belgium.",
            },
            {
                "source": "Source B",
                "url": "https://example.com/b",
                "text": "Axon Group has 250 employees and 6 locations in Belgium.",
            },
        ]
    )
    passed = bool(contradictions) and any(
        str(item.get("type") or "") == "numeric_mismatch"
        for item in contradictions
        if isinstance(item, dict)
    )
    return {
        "id": "contradiction_risk_signal",
        "category": "contradiction_risk",
        "passed": passed,
        "detail": str(contradictions[:2]),
    }


def _evaluate_case_depth_profile_for_deep_research() -> dict[str, Any]:
    with patch(
        "api.services.agent.research_depth_profile.call_json_response",
        return_value={
            "tier": "deep_research",
            "rationale": "Deep research needed.",
            "source_budget_min": 50,
            "source_budget_max": 100,
            "max_query_variants": 8,
            "results_per_query": 12,
            "fused_top_k": 100,
            "max_live_inspections": 24,
            "min_unique_sources": 50,
            "min_keywords": 18,
            "simple_explanation_required": False,
            "include_execution_why": False,
        },
    ):
        profile = derive_research_depth_profile(
            message="Research energy market trends from 50-100 websites and papers with citations.",
            agent_goal="Detailed deep research report",
            user_preferences={"audience": "executive"},
            agent_mode="company_agent",
        )
    passed = (
        profile.tier == "deep_research"
        and profile.source_budget_min >= 50
        and profile.source_budget_max >= 100
        and profile.max_query_variants >= 8
    )
    return {
        "id": "depth_profile_for_deep_research",
        "category": "depth_routing",
        "passed": passed,
        "detail": str(profile.as_dict()),
    }


def _evaluate_case_child_friendly_profile_flag() -> dict[str, Any]:
    with patch(
        "api.services.agent.research_depth_profile.call_json_response",
        return_value={
            "tier": "standard",
            "rationale": "Simple explanation requested.",
            "simple_explanation_required": True,
            "include_execution_why": False,
        },
    ):
        profile = derive_research_depth_profile(
            message="Explain machine learning so a 5 year old can understand in simple terms.",
            agent_goal="",
            user_preferences={"audience": "beginner"},
            agent_mode="company_agent",
        )
    passed = bool(profile.simple_explanation_required)
    return {
        "id": "child_friendly_profile_flag",
        "category": "depth_routing",
        "passed": passed,
        "detail": str(profile.as_dict()),
    }


def _evaluate_case_citation_gate_deep_threshold() -> dict[str, Any]:
    with _temporary_env({"MAIA_AGENT_LLM_VERIFICATION_ENABLED": "0"}):
        report = build_verification_report(
            task=TaskIntelligence(
                objective="Deep energy research report",
                target_url="",
                target_host="",
                delivery_email="",
                requires_delivery=False,
                requires_web_inspection=True,
                requested_report=True,
                intent_tags=("web_research", "report_generation"),
            ),
            planned_tool_ids=["marketing.web_research", "report.generate"],
            executed_steps=[],
            actions=[],
            sources=[],
            runtime_settings={
                "__research_depth_tier": "deep_research",
                "__research_min_unique_sources": 50,
            },
        )
    passed = bool(report.get("citation_gate_passed") is False and report.get("citation_gate_threshold") == 0.85)
    return {
        "id": "citation_gate_deep_threshold",
        "category": "citation_quality",
        "passed": passed,
        "detail": str(
            {
                "citation_gate_passed": report.get("citation_gate_passed"),
                "citation_gate_threshold": report.get("citation_gate_threshold"),
                "checks": report.get("checks"),
            }
        ),
    }


def run_agent_eval_suite() -> dict[str, Any]:
    fixture_rows = _load_eval_fixtures()
    fixture_ids = {row["id"] for row in fixture_rows}

    cases = [
        _evaluate_case_ambiguity_missing_requirements(),
        _evaluate_case_multi_intent_fact_coverage(),
        _evaluate_case_external_action_block_unverified_facts(),
        _evaluate_case_delivery_ready_when_contract_satisfied(),
        _evaluate_case_contradiction_risk_signal(),
        _evaluate_case_depth_profile_for_deep_research(),
        _evaluate_case_child_friendly_profile_flag(),
        _evaluate_case_citation_gate_deep_threshold(),
    ]
    implemented_ids = {str(case.get("id") or "") for case in cases}
    missing_fixture_cases = sorted(list(fixture_ids - implemented_ids))

    total = max(1, len(cases))
    passed_total = sum(1 for case in cases if case.get("passed"))
    overall_pass_rate = round(passed_total / float(total), 4)

    category_scores: dict[str, float] = {}
    for category in sorted({str(case.get("category") or "") for case in cases if str(case.get("category") or "")}):
        category_rows = [case for case in cases if str(case.get("category") or "") == category]
        passed = sum(1 for case in category_rows if case.get("passed"))
        category_scores[category] = round(passed / float(max(1, len(category_rows))), 4)

    gates = {
        "overall_pass_rate": overall_pass_rate >= EVAL_THRESHOLDS["overall_pass_rate"],
        "ambiguity": category_scores.get("ambiguity", 0.0) >= EVAL_THRESHOLDS["ambiguity"],
        "multi_intent": category_scores.get("multi_intent", 0.0) >= EVAL_THRESHOLDS["multi_intent"],
        "delivery_completeness": category_scores.get("delivery_completeness", 0.0)
        >= EVAL_THRESHOLDS["delivery_completeness"],
        "contradiction_risk": category_scores.get("contradiction_risk", 0.0)
        >= EVAL_THRESHOLDS["contradiction_risk"],
        "depth_routing": category_scores.get("depth_routing", 0.0)
        >= EVAL_THRESHOLDS["depth_routing"],
        "citation_quality": category_scores.get("citation_quality", 0.0)
        >= EVAL_THRESHOLDS["citation_quality"],
        "fixtures_synced": not missing_fixture_cases,
    }
    return {
        "thresholds": dict(EVAL_THRESHOLDS),
        "cases": cases,
        "case_count": len(cases),
        "pass_count": passed_total,
        "overall_pass_rate": overall_pass_rate,
        "category_scores": category_scores,
        "gates": gates,
        "fixture_case_count": len(fixture_rows),
        "missing_fixture_cases": missing_fixture_cases,
    }
