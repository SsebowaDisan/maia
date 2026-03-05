from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation


@dataclass(slots=True, frozen=True)
class WorkspaceLoggingPlan:
    workspace_logging_requested: bool
    deep_workspace_logging_enabled: bool


def build_workspace_logging_plan(
    *,
    request: ChatRequest,
    settings: dict[str, Any],
    task_prep: TaskPreparation,
    deep_research_mode: bool,
) -> WorkspaceLoggingPlan:
    intent_tags = {
        str(tag).strip().lower()
        for tag in getattr(task_prep.task_intelligence, "intent_tags", [])
        if str(tag).strip()
    }
    workspace_logging_requested = bool(
        ("create_document" in task_prep.contract_actions)
        or ("update_sheet" in task_prep.contract_actions)
        or ("docs_write" in intent_tags)
        or ("sheets_update" in intent_tags)
    )
    always_workspace_logging = request.agent_mode == "company_agent" and bool(
        settings.get("agent.company_agent_always_workspace_logging", False)
    )
    deep_workspace_logging_enabled = always_workspace_logging or (
        workspace_logging_requested
        or (
            deep_research_mode
            and bool(settings.get("agent.deep_research_workspace_logging", False))
        )
    )
    return WorkspaceLoggingPlan(
        workspace_logging_requested=workspace_logging_requested,
        deep_workspace_logging_enabled=deep_workspace_logging_enabled,
    )


def prepend_workspace_roadmap_steps(
    *,
    request: ChatRequest,
    task_prep: TaskPreparation,
    steps: list[PlannedStep],
    planned_search_terms: list[str],
    planned_keywords: list[str],
) -> list[PlannedStep]:
    search_preview = ", ".join(planned_search_terms[:4]) if planned_search_terms else "n/a"
    keyword_preview = ", ".join(planned_keywords[:10]) if planned_keywords else "n/a"
    roadmap_steps: list[PlannedStep] = [
        PlannedStep(
            tool_id="workspace.sheets.track_step",
            title="Open execution roadmap in Google Sheets",
            params={
                "step_name": "Execution roadmap initialized",
                "status": "planned",
                "detail": (
                    f"Search terms: {search_preview} | Keywords: {keyword_preview}"
                ),
                "__workspace_logging_step": True,
            },
        ),
    ]
    for idx, planned_step in enumerate(steps, start=1):
        roadmap_steps.append(
            PlannedStep(
                tool_id="workspace.sheets.track_step",
                title=f"Roadmap step {idx}: {planned_step.title}",
                params={
                    "step_name": f"{idx}. {planned_step.title}",
                    "status": "planned",
                    "detail": (
                        f"Tool={planned_step.tool_id} | "
                        f"Search terms={search_preview} | "
                        f"Keywords={keyword_preview}"
                    )[:900],
                    "__workspace_logging_step": True,
                },
            )
        )
    return roadmap_steps + steps
