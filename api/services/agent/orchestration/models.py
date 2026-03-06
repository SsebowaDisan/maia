from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.services.agent.models import AgentAction, AgentSource
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext


@dataclass(slots=True)
class TaskPreparation:
    task_intelligence: Any
    user_preferences: dict[str, Any]
    research_depth_profile: dict[str, Any]
    conversation_summary: str
    rewritten_task: str
    planned_deliverables: list[str]
    planned_constraints: list[str]
    task_contract: dict[str, Any]
    contract_objective: str
    contract_outputs: list[str]
    contract_facts: list[str]
    contract_actions: list[str]
    contract_target: str
    contract_missing_requirements: list[str]
    contract_success_checks: list[str]
    memory_context_snippets: list[str]
    clarification_blocked: bool
    clarification_questions: list[str]


@dataclass(slots=True)
class PlanPreparation:
    steps: list[PlannedStep]
    deep_research_mode: bool
    highlight_color: str
    planned_search_terms: list[str]
    planned_keywords: list[str]
    workspace_logging_requested: bool
    deep_workspace_logging_enabled: bool
    delivery_email: str


@dataclass(slots=True)
class ExecutionState:
    execution_context: ToolExecutionContext
    all_actions: list[AgentAction] = field(default_factory=list)
    all_sources: list[AgentSource] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    executed_steps: list[dict[str, Any]] = field(default_factory=list)
    contract_check_result: dict[str, Any] = field(
        default_factory=lambda: {
            "ready_for_final_response": True,
            "ready_for_external_actions": True,
            "missing_items": [],
            "reason": "",
            "recommended_remediation": [],
        }
    )
    remediation_attempts: int = 0
    max_remediation_attempts: int = 2
    remediation_signatures: set[str] = field(default_factory=set)
    deep_workspace_logging_enabled: bool = False
    deep_workspace_docs_logging_enabled: bool = False
    deep_workspace_sheets_logging_enabled: bool = False
    deep_workspace_warning_emitted: bool = False
    dynamic_inspection_inserted: bool = False
    research_retry_inserted: bool = False
