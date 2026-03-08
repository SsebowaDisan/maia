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
    contract_missing_slots: list[dict[str, Any]] = field(default_factory=list)
    session_context_snippets: list[str] = field(default_factory=list)
    working_context: dict[str, Any] = field(default_factory=dict)


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
    role_owned_steps: list[dict[str, Any]] = field(default_factory=list)


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
    retry_trace: list[dict[str, Any]] = field(default_factory=list)
    remediation_trace: list[dict[str, Any]] = field(default_factory=list)
    parallel_research_trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class TrustVerdict:
    """JUDGE trust gate output for a research response."""
    trust_score: float  # 0.0–1.0
    gate_color: str     # "green" | "amber" | "red"
    reason: str         # human-readable explanation
    contested_claim_count: int = 0
    resolved_claim_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trust_score": round(self.trust_score, 3),
            "gate_color": self.gate_color,
            "reason": self.reason,
            "contested_claim_count": self.contested_claim_count,
            "resolved_claim_count": self.resolved_claim_count,
        }


@dataclass(slots=True, frozen=True)
class ResearchOutputContract:
    """Typed output contract for SCOUT research results."""
    source_count: int
    unique_url_count: int
    depth_tier: str
    providers_used: list[str]
    coverage_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_count": self.source_count,
            "unique_url_count": self.unique_url_count,
            "depth_tier": self.depth_tier,
            "providers_used": self.providers_used,
            "coverage_ok": self.coverage_ok,
        }


@dataclass(slots=True, frozen=True)
class ClaimMatrixContract:
    """Typed output contract for ORACLE claim-matrix results."""
    claim_count: int
    overall_trust_score: float
    overall_gate_color: str
    contested_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_count": self.claim_count,
            "overall_trust_score": round(self.overall_trust_score, 3),
            "overall_gate_color": self.overall_gate_color,
            "contested_count": self.contested_count,
        }
