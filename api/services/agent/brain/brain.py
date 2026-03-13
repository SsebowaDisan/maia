"""Brain — the reactive coordinator for one agent turn.

The Brain sits between the step executor and the LLM stack.  After every
tool step it:
  1. Records the outcome in BrainState (evidence pool + step history)
  2. Runs LLM-based semantic coverage checking (coverage.py)
  3. Generates a forward-looking step rationale (discussion.py)
  4. Generates a post-step inner-monologue thought (discussion.py)
  5. Emits brain_thinking / brain_coverage events for the UI panel
  6. Returns a BrainDirective: continue / add_steps / halt

The Brain never hard-codes keywords or decision trees.
Every decision is made by an LLM call in coverage.py, reviser.py,
or discussion.py.

Environment
-----------
MAIA_BRAIN_ENABLED   (default "true") — set "false" to disable Brain entirely
                      and make execute_planned_steps behave as before.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Generator
from typing import Any

from api.services.agent.planner_models import PlannedStep

from .coverage import update_coverage
from .discussion import generate_step_rationale, generate_step_thought
from .reviser import build_revision_steps
from .signals import BrainDirective, BrainSignal, StepOutcome
from .state import ActionCoverage, BrainState, FactCoverage

logger = logging.getLogger(__name__)

_ENABLED = os.environ.get("MAIA_BRAIN_ENABLED", "true").lower() != "false"


class Brain:
    """Reactive coordinator attached to one agent turn.

    Instantiated once per ``run_stream`` call, after task_prep + plan_prep
    are complete so the task contract is available.

    Parameters
    ----------
    state:
        Pre-populated BrainState including the task contract.
    registry:
        Tool registry (passed through to reviser for available-tool listing).
    """

    def __init__(self, *, state: BrainState, registry: Any) -> None:
        self.state = state
        self.registry = registry
        self._total_steps = len(state.original_plan)

    # ------------------------------------------------------------------
    # Public helpers called by the orchestrator / step executor
    # ------------------------------------------------------------------

    def pre_step_rationale(
        self,
        *,
        step: PlannedStep,
        step_index: int,
    ) -> str:
        """Generate a forward-looking rationale string before a step runs.

        Returned string is suitable for inclusion in a ``tool_started``
        or custom ``brain_rationale`` event detail field.
        """
        if not _ENABLED:
            return step.why_this_step

        return generate_step_rationale(
            state=self.state,
            step_index=step_index,
            total_steps=self._total_steps,
            tool_id=step.tool_id,
            step_title=step.title,
            why_this_step=step.why_this_step,
            expected_evidence=step.expected_evidence,
        )

    def observe_step(
        self,
        *,
        signal: BrainSignal,
        steps: list[PlannedStep],
        emit_event: Any,
        activity_event_factory: Any,
    ) -> Generator[dict[str, Any], None, BrainDirective]:
        """Called after every tool step.

        Mutates ``state`` and optionally extends ``steps`` in-place.
        Yields UI events (brain_thinking, brain_coverage, brain_revision).
        Returns a BrainDirective telling the executor what to do next.
        """
        if not _ENABLED:
            return BrainDirective(action="continue")

        outcome = signal.outcome
        self.state.record_outcome(outcome)
        self._total_steps = len(steps)
        revisions_remaining = self.state.max_revisions - self.state.revision_count

        # 1. Semantic coverage check
        coverage_events = update_coverage(state=self.state, outcome=outcome)
        for ev in coverage_events:
            cov_event = activity_event_factory(
                event_type="brain_coverage",
                title=f"Coverage: {ev.get('type', 'update')}",
                detail=str(ev.get("reason", ""))[:200],
                metadata=ev,
            )
            yield emit_event(cov_event)

        # 2. Post-step inner monologue
        thought = generate_step_thought(
            state=self.state,
            outcome=outcome,
            step_title=_step_title_for(steps, outcome.step_index),
            total_steps=self._total_steps,
            revisions_remaining=revisions_remaining,
        )
        if thought:
            think_event = activity_event_factory(
                event_type="brain_thinking",
                title="Brain thinking",
                detail=thought,
                metadata={
                    "step_index": outcome.step_index,
                    "tool_id": outcome.tool_id,
                    "coverage_ratio": self.state.fact_coverage.coverage_ratio(),
                },
            )
            yield emit_event(think_event)

        # 3. Decide what to do next
        directive = self._assess(steps=steps)

        if directive.action == "add_steps":
            rev_event = activity_event_factory(
                event_type="brain_revision",
                title=f"Plan revised: +{len(directive.injected_steps)} step(s)",
                detail=directive.directive_reason[:200],
                metadata={
                    "injected_count": len(directive.injected_steps),
                    "revision_count": self.state.revision_count,
                    "gap_summary": self.state.gap_summary()[:200],
                },
            )
            yield emit_event(rev_event)
            # Extend steps list in-place so the executor picks them up.
            for s in directive.injected_steps:
                if isinstance(s, PlannedStep):
                    steps.append(s)
                elif isinstance(s, dict):
                    steps.append(PlannedStep(
                        tool_id=str(s.get("tool_id", "")),
                        title=str(s.get("title", ""))[:120],
                        params=s.get("params") or {},
                        why_this_step=str(s.get("why_this_step", ""))[:200],
                        expected_evidence=tuple(s.get("expected_evidence") or []),
                    ))

        elif directive.action == "halt":
            halt_event = activity_event_factory(
                event_type="brain_halt",
                title="Brain halting execution",
                detail=str(directive.halt_reason or "")[:200],
                metadata={
                    "halt_reason": directive.halt_reason,
                    "directive_reason": directive.directive_reason,
                    "coverage_ratio": self.state.fact_coverage.coverage_ratio(),
                },
            )
            yield emit_event(halt_event)

        return directive

    # ------------------------------------------------------------------
    # Internal assessment logic
    # ------------------------------------------------------------------

    def _assess(self, *, steps: list[PlannedStep]) -> BrainDirective:
        """Decide the next directive based on current state.

        Order of checks:
        1. Contract fully satisfied → halt (done)
        2. More planned steps remain → continue
        3. Gaps remain + revision budget available → add_steps
        4. No budget left → halt (best-effort)
        """
        satisfied = self.state.contract_satisfied()
        remaining = _remaining_step_count(steps, len(self.state.step_outcomes))

        if satisfied:
            self.state.halt_reason = "contract_satisfied"
            return BrainDirective(
                action="halt",
                halt_reason="contract_satisfied",
                directive_reason="All required facts and actions are covered.",
                brain_thought="",
            )

        if remaining > 0:
            return BrainDirective(
                action="continue",
                directive_reason=f"{remaining} planned step(s) remaining.",
            )

        # No more planned steps — try to revise if budget allows.
        if self.state.can_revise():
            new_steps = build_revision_steps(
                state=self.state,
                registry=self.registry,
            )
            if new_steps:
                self.state.revision_count += 1
                reason = (
                    f"Revision {self.state.revision_count}: "
                    f"adding {len(new_steps)} step(s) to cover: "
                    f"{self.state.gap_summary()[:120]}"
                )
                return BrainDirective(
                    action="add_steps",
                    injected_steps=list(new_steps),  # type: ignore[arg-type]
                    directive_reason=reason,
                )

        # Budget exhausted or reviser returned nothing.
        gap = self.state.gap_summary()
        self.state.halt_reason = "budget_exhausted"
        return BrainDirective(
            action="halt",
            halt_reason="budget_exhausted",
            directive_reason=f"Revision budget exhausted. Remaining gaps: {gap[:120]}",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _step_title_for(steps: list[PlannedStep], step_index: int) -> str:
    """Return the title for the step at `step_index` (1-based display index)."""
    idx = step_index - 1
    if 0 <= idx < len(steps):
        return steps[idx].title
    return f"Step {step_index}"


def _remaining_step_count(steps: list[PlannedStep], executed: int) -> int:
    """Count how many steps in the list have not been executed yet."""
    return max(0, len(steps) - executed)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_brain(
    *,
    turn_id: str,
    user_id: str,
    conversation_id: str,
    user_message: str,
    task_intelligence: Any,
    task_contract: dict[str, Any],
    original_plan: list[PlannedStep],
    registry: Any,
) -> Brain:
    """Construct a Brain with a fully initialised BrainState.

    Called by AgentOrchestrator.run_stream() after task_prep + plan_prep.
    """
    required_facts: list[str] = []
    required_actions: list[str] = []
    if isinstance(task_contract, dict):
        rf = task_contract.get("required_facts") or []
        ra = task_contract.get("required_actions") or []
        required_facts = [str(f) for f in rf if f]
        required_actions = [str(a) for a in ra if a]

    fact_coverage = FactCoverage(required_facts=required_facts)
    action_coverage = ActionCoverage(required_actions=required_actions)

    state = BrainState(
        turn_id=turn_id,
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=user_message,
        task_intelligence=task_intelligence,
        task_contract=task_contract,
        original_plan=list(original_plan),
        fact_coverage=fact_coverage,
        action_coverage=action_coverage,
    )
    return Brain(state=state, registry=registry)
