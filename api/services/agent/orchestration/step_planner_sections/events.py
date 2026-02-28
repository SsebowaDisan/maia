from __future__ import annotations

from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation


def plan_decompose_started_event(
    *,
    activity_event_factory,
    task_prep: TaskPreparation,
    planning_detail: str,
    request_message: str,
) -> AgentActivityEvent:
    return activity_event_factory(
        event_type="llm.plan_decompose_started",
        title="Breaking rewritten task into execution steps",
        detail=planning_detail[:200],
        metadata={
            "detailed_task": task_prep.rewritten_task or request_message,
            "deliverables": task_prep.planned_deliverables,
            "constraints": task_prep.planned_constraints,
        },
    )


def plan_decompose_completed_event(
    *,
    activity_event_factory,
    steps: list[PlannedStep],
) -> AgentActivityEvent:
    return activity_event_factory(
        event_type="llm.plan_decompose_completed",
        title="Step decomposition ready",
        detail=f"Generated {len(steps)} initial step(s).",
        metadata={"step_count": len(steps), "tool_ids": [step.tool_id for step in steps]},
    )


def plan_step_event(
    *,
    activity_event_factory,
    step_number: int,
    planned_step: PlannedStep,
) -> AgentActivityEvent:
    return activity_event_factory(
        event_type="llm.plan_step",
        title=f"Planned step {step_number}",
        detail=f"{planned_step.title} ({planned_step.tool_id})",
        metadata={
            "step": step_number,
            "title": planned_step.title,
            "tool_id": planned_step.tool_id,
            "params": planned_step.params,
            "why_this_step": planned_step.why_this_step,
            "expected_evidence": list(planned_step.expected_evidence),
        },
    )


def plan_candidate_event(
    *,
    activity_event_factory,
    steps: list[PlannedStep],
    task_prep: TaskPreparation,
    request_message: str,
    delivery_email: str,
    workspace_logging_requested: bool,
    planned_search_terms: list[str],
    planned_keywords: list[str],
) -> AgentActivityEvent:
    return activity_event_factory(
        event_type="plan_candidate",
        title="Generated initial execution plan",
        detail=f"Parsed task into {len(steps)} concrete execution step(s).",
        metadata={
            "steps": [step.__dict__ for step in steps],
            "task_understanding": {
                "objective": task_prep.task_intelligence.objective,
                "delivery_email": delivery_email,
                "workspace_logging_requested": workspace_logging_requested,
                "target_url": task_prep.task_intelligence.target_url,
                "detailed_task": task_prep.rewritten_task or request_message,
                "deliverables": task_prep.planned_deliverables[:6],
                "constraints": task_prep.planned_constraints[:6],
                "contract_objective": task_prep.contract_objective,
                "contract_required_outputs": task_prep.contract_outputs[:6],
                "contract_required_facts": task_prep.contract_facts[:6],
                "contract_required_actions": task_prep.contract_actions[:6],
                "contract_delivery_target": task_prep.contract_target,
                "contract_missing_requirements": task_prep.contract_missing_requirements[:6],
                "contract_success_checks": task_prep.contract_success_checks[:8],
                "planned_search_terms": planned_search_terms[:6],
                "planned_keywords": planned_keywords[:12],
            },
        },
    )


def plan_refined_event(
    *,
    activity_event_factory,
    steps: list[PlannedStep],
    planned_search_terms: list[str],
    planned_keywords: list[str],
    fact_coverage: dict[str, object] | None = None,
) -> AgentActivityEvent:
    return activity_event_factory(
        event_type="plan_refined",
        title="Refined execution order",
        detail="Prioritized sequence with search terms and keyword blueprint",
        metadata={
            "step_ids": [step.tool_id for step in steps],
            "search_terms": planned_search_terms[:6],
            "keywords": planned_keywords[:12],
            "fact_coverage": fact_coverage if isinstance(fact_coverage, dict) else {},
        },
    )


def plan_fact_coverage_event(
    *,
    activity_event_factory,
    fact_coverage: dict[str, object],
) -> AgentActivityEvent:
    missing_facts = [
        str(item).strip()
        for item in (
            fact_coverage.get("missing_facts") if isinstance(fact_coverage, dict) else []
        )
        if str(item).strip()
    ]
    coverage_text = (
        f"{int(fact_coverage.get('covered_fact_count') or 0)}/"
        f"{int(fact_coverage.get('required_fact_count') or 0)} required fact(s) mapped to evidence."
    )
    detail = coverage_text if not missing_facts else coverage_text + " Missing: " + "; ".join(missing_facts[:3])
    return activity_event_factory(
        event_type="llm.plan_fact_coverage",
        title="Plan fact coverage check",
        detail=detail,
        metadata={
            "required_fact_count": int(fact_coverage.get("required_fact_count") or 0),
            "covered_fact_count": int(fact_coverage.get("covered_fact_count") or 0),
            "missing_facts": missing_facts[:6],
            "fact_step_map": (
                fact_coverage.get("fact_step_map")
                if isinstance(fact_coverage.get("fact_step_map"), dict)
                else {}
            ),
        },
    )


def plan_ready_event(*, activity_event_factory, steps: list[PlannedStep]) -> AgentActivityEvent:
    return activity_event_factory(
        event_type="plan_ready",
        title=f"Prepared {len(steps)} execution steps",
        metadata={"steps": [step.__dict__ for step in steps]},
    )
