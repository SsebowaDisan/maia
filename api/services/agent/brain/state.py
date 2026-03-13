"""BrainState — the Brain's working memory for one agent turn.

Holds everything the Brain has learned since turn start:
- The task contract (required facts + actions derived from user goal)
- What steps ran and what they produced
- Coverage tracking (which contract items are satisfied)
- Evidence pool (all content summaries accumulated)
- Revision budget and timing
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from .signals import StepOutcome

_MAX_REVISIONS = int(os.environ.get("MAIA_BRAIN_MAX_REVISIONS", "2"))
_MAX_REVISION_STEPS = int(os.environ.get("MAIA_BRAIN_MAX_REVISION_STEPS", "3"))


# ---------------------------------------------------------------------------
# Coverage helpers
# ---------------------------------------------------------------------------

@dataclass
class FactCoverage:
    """Tracks which required_facts from the task contract are satisfied.

    Keys in ``covered`` are the exact strings from the contract's
    ``required_facts`` list.  Values are set by the LLM coverage checker
    (brain/coverage.py) after each step.
    """
    required_facts: list[str] = field(default_factory=list)
    covered: dict[str, bool] = field(default_factory=dict)
    # fact → list of tool_ids that contributed evidence
    evidence_sources: dict[str, list[str]] = field(default_factory=dict)

    def mark_covered(self, fact: str, tool_id: str) -> None:
        self.covered[fact] = True
        self.evidence_sources.setdefault(fact, []).append(tool_id)

    def uncovered_facts(self) -> list[str]:
        return [f for f in self.required_facts if not self.covered.get(f)]

    def coverage_ratio(self) -> float:
        if not self.required_facts:
            return 1.0
        return sum(1 for f in self.required_facts if self.covered.get(f)) / len(self.required_facts)

    def is_complete(self) -> bool:
        return bool(self.required_facts) and all(
            self.covered.get(f) for f in self.required_facts
        )


@dataclass
class ActionCoverage:
    """Tracks which required_actions from the task contract are completed."""
    required_actions: list[str] = field(default_factory=list)
    completed: dict[str, bool] = field(default_factory=dict)

    def mark_completed(self, action: str) -> None:
        self.completed[action] = True

    def uncompleted_actions(self) -> list[str]:
        return [a for a in self.required_actions if not self.completed.get(a)]

    def is_complete(self) -> bool:
        if not self.required_actions:
            return True
        return all(self.completed.get(a) for a in self.required_actions)


# ---------------------------------------------------------------------------
# BrainState
# ---------------------------------------------------------------------------

@dataclass
class BrainState:
    """All working memory for one Brain turn.

    Created at turn start; mutated by Brain.observe_step(); read by
    coverage / reviser / discussion LLM callers.
    """
    turn_id: str
    user_id: str
    conversation_id: str

    # Original user message — attached to every LLM decision.
    user_message: str

    # Task intelligence from task_understanding.py (TaskIntelligence instance).
    task_intelligence: Any

    # Contract dict from llm_contracts.build_task_contract().
    task_contract: dict[str, Any]

    # The plan as originally constructed.
    original_plan: list[Any]  # list[PlannedStep]

    # Coverage trackers — populated from contract at Brain init.
    fact_coverage: FactCoverage = field(default_factory=FactCoverage)
    action_coverage: ActionCoverage = field(default_factory=ActionCoverage)

    # Accumulated outcomes from each step.
    step_outcomes: list[StepOutcome] = field(default_factory=list)

    # Summaries of content found — fed into revision + discussion prompts.
    evidence_pool: list[str] = field(default_factory=list)

    # Running count of plan revisions this turn.
    revision_count: int = 0
    max_revisions: int = field(default_factory=lambda: _MAX_REVISIONS)
    max_revision_steps: int = field(default_factory=lambda: _MAX_REVISION_STEPS)

    # Set when Brain decides to stop.
    halt_reason: str | None = None

    started_at_ms: int = field(default_factory=lambda: int(time.monotonic() * 1000))

    def elapsed_ms(self) -> int:
        return int(time.monotonic() * 1000) - self.started_at_ms

    def can_revise(self) -> bool:
        return self.revision_count < self.max_revisions

    def record_outcome(self, outcome: StepOutcome) -> None:
        self.step_outcomes.append(outcome)
        if outcome.content_summary.strip():
            self.evidence_pool.append(
                f"[{outcome.tool_id}] {outcome.content_summary[:400]}"
            )

    def executed_tool_ids(self) -> list[str]:
        return [o.tool_id for o in self.step_outcomes]

    def contract_satisfied(self) -> bool:
        """True when every required fact and action is covered.

        If the contract has no requirements, returns True only when at
        least one non-empty evidence item exists (best-effort).
        """
        has_facts = bool(self.fact_coverage.required_facts)
        has_actions = bool(self.action_coverage.required_actions)
        if not has_facts and not has_actions:
            return bool(self.evidence_pool)
        facts_ok = self.fact_coverage.is_complete() if has_facts else True
        actions_ok = self.action_coverage.is_complete() if has_actions else True
        return facts_ok and actions_ok

    def gap_summary(self) -> str:
        """Short human/LLM-readable description of what is still missing."""
        parts: list[str] = []
        uncovered = self.fact_coverage.uncovered_facts()
        if uncovered:
            parts.append("Missing facts: " + "; ".join(uncovered[:6]))
        unfinished = self.action_coverage.uncompleted_actions()
        if unfinished:
            parts.append("Pending actions: " + "; ".join(unfinished[:4]))
        return "  ".join(parts) if parts else "No specific gaps identified."

    def evidence_summary(self) -> str:
        """Compact summary of all evidence found so far."""
        if not self.evidence_pool:
            return "No evidence collected yet."
        lines = self.evidence_pool[-8:]  # last 8 entries
        return "\n".join(lines)

    def objective(self) -> str:
        """User-facing objective string from task intelligence."""
        return str(
            getattr(self.task_intelligence, "objective", None)
            or self.user_message
        )[:300]
