from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from api.schemas import ChatRequest
from api.services.agent.planner import PlannedStep

from ..models import TaskPreparation

DOCS_REQUEST_RE = re.compile(r"\bgoogle\s+docs?\b|\bdocs?\b", re.IGNORECASE)
SHEETS_REQUEST_RE = re.compile(
    r"\bgoogle\s+sheets?\b|\bspreadsheet(?:s)?\b|\bsheets?\b",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class WorkspaceLoggingPlan:
    workspace_logging_requested: bool
    deep_workspace_logging_enabled: bool


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    token = " ".join(str(value or "").split()).strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _explicit_workspace_output_flags(request: ChatRequest) -> tuple[bool, bool]:
    message_text = " ".join(str(request.message or "").split()).strip()
    # Restrict opt-in to explicit terms in the current user message only.
    # Do not trust inferred LLM tags here; false positives can trigger
    # unwanted Docs/Sheets steps and theatre surfaces.
    docs_requested = bool(DOCS_REQUEST_RE.search(message_text))
    sheets_requested = bool(SHEETS_REQUEST_RE.search(message_text))
    return docs_requested, sheets_requested


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
    contract_or_intent_docs_requested = bool(
        ("create_document" in task_prep.contract_actions)
        or ("docs_write" in intent_tags)
    )
    contract_or_intent_sheets_requested = bool(
        ("update_sheet" in task_prep.contract_actions)
        or ("sheets_update" in intent_tags)
    )
    explicit_docs_requested, explicit_sheets_requested = _explicit_workspace_output_flags(
        request
    )
    require_explicit_workspace_request = _coerce_bool(
        settings.get("agent.workspace_logging_require_user_request"),
        default=True,
    )
    if require_explicit_workspace_request:
        docs_requested = explicit_docs_requested
        sheets_requested = explicit_sheets_requested
    else:
        docs_requested = contract_or_intent_docs_requested or explicit_docs_requested
        sheets_requested = contract_or_intent_sheets_requested or explicit_sheets_requested
    workspace_logging_requested = docs_requested or sheets_requested
    always_workspace_logging = request.agent_mode == "company_agent" and bool(
        settings.get("agent.company_agent_always_workspace_logging", False)
    )
    deep_research_workspace_logging_enabled = deep_research_mode and bool(
        settings.get("agent.deep_research_workspace_logging", False)
    )
    if require_explicit_workspace_request and not sheets_requested:
        # Optional roadmap + shadow logging should stay off unless Sheets output
        # was explicitly requested by the user.
        deep_workspace_logging_enabled = False
    else:
        deep_workspace_logging_enabled = (
            sheets_requested
            or always_workspace_logging
            or deep_research_workspace_logging_enabled
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
