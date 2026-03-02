from __future__ import annotations

from typing import Any

from api.schemas import ChatRequest
from api.services.agent.models import AgentAction, AgentSource
from api.services.agent.planner import PlannedStep

from .artifacts import append_files_and_documents
from .citations import append_evidence_citations
from .delivery import append_contract_gate, append_delivery_status
from .models import AnswerBuildContext
from .plan import append_execution_plan
from .summary import append_execution_issues, append_execution_summary, append_key_findings
from .understanding import append_task_understanding
from .value_add import append_evidence_backed_value_add
from .verification import append_recommended_next_steps, append_verification


def compose_professional_answer(
    *,
    request: ChatRequest,
    planned_steps: list[PlannedStep],
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    sources: list[AgentSource],
    next_steps: list[str],
    runtime_settings: dict[str, Any],
    verification_report: dict[str, Any] | None = None,
) -> str:
    ctx = AnswerBuildContext(
        request=request,
        planned_steps=planned_steps,
        executed_steps=executed_steps,
        actions=actions,
        sources=sources,
        next_steps=next_steps,
        runtime_settings=runtime_settings,
        verification_report=verification_report,
    )

    lines: list[str] = []
    append_task_understanding(lines, ctx)
    append_execution_plan(lines, ctx)
    append_execution_summary(lines, ctx)
    append_key_findings(lines, ctx)
    append_delivery_status(lines, ctx)
    append_contract_gate(lines, ctx)
    append_execution_issues(lines, ctx)
    append_files_and_documents(lines, ctx)
    append_verification(lines, ctx)
    append_evidence_backed_value_add(lines, ctx)
    append_evidence_citations(lines, ctx)
    append_recommended_next_steps(lines, ctx)
    return "\n".join(lines)
