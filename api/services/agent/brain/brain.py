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

# Strategy detector (Innovation #10) — optional import, try/except wrapped
try:
    from api.services.agent.reflection import StrategyDetector
    _STRATEGY_DETECTOR_AVAILABLE = True
except Exception:
    _STRATEGY_DETECTOR_AVAILABLE = False

# Multi-hypothesis tracker (Innovation #2) — optional import, try/except wrapped
try:
    from api.services.agent.reasoning.hypothesis_tracker import HypothesisTracker
    _HYPOTHESIS_TRACKER_AVAILABLE = True
except Exception:
    _HYPOTHESIS_TRACKER_AVAILABLE = False

logger = logging.getLogger(__name__)

# Lazy-loaded tool composer (Innovation #9)
_tool_composer = None


def _get_tool_composer():
    """Lazy-load ToolComposer to avoid circular imports."""
    global _tool_composer
    if _tool_composer is None:
        try:
            from api.services.agent.reasoning.tool_composer import ToolComposer
            _tool_composer = ToolComposer()
        except Exception as exc:
            logger.debug("brain.tool_composer_init_failed error=%s", exc)
            _tool_composer = None
    return _tool_composer


# Lazy-loaded CausalDAG instance (Innovation #4)
_causal_dag_instance = None


def _get_causal_dag():
    """Lazy-load CausalDAG to avoid circular imports."""
    global _causal_dag_instance
    if _causal_dag_instance is None:
        try:
            from api.services.agent.reasoning.causal_dag import CausalDAG
            _causal_dag_instance = CausalDAG()
        except Exception as exc:
            logger.debug("brain.causal_dag_init_failed error=%s", exc)
            _causal_dag_instance = None
    return _causal_dag_instance


# Lazy-loaded prospective reasoner instance (avoids import cost when disabled).
_prospective_reasoner = None


def _get_prospective_reasoner():
    """Lazy-load ProspectiveReasoner to avoid circular imports."""
    global _prospective_reasoner
    if _prospective_reasoner is None:
        try:
            from api.services.agent.reasoning.prospective import ProspectiveReasoner
            _prospective_reasoner = ProspectiveReasoner()
        except Exception as exc:
            logger.debug("brain.prospective_reasoner_init_failed error=%s", exc)
            _prospective_reasoner = None
    return _prospective_reasoner

_ENABLED = os.environ.get("MAIA_BRAIN_ENABLED", "true").lower() != "false"

# Advanced memory subsystems (lazy-loaded, never block core Brain logic).
_semantic_memory = None
_tool_pattern_db = None


def _get_semantic_memory():
    global _semantic_memory
    if _semantic_memory is None:
        from api.services.agent.memory.semantic_memory import SemanticMemoryStore
        _semantic_memory = SemanticMemoryStore()
    return _semantic_memory


def _get_tool_pattern_db():
    global _tool_pattern_db
    if _tool_pattern_db is None:
        from api.services.agent.memory.tool_patterns import get_tool_pattern_db
        _tool_pattern_db = get_tool_pattern_db()
    return _tool_pattern_db


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
        # Innovation #2: multi-hypothesis tracker
        self._hypothesis_tracker: HypothesisTracker | None = None
        if _HYPOTHESIS_TRACKER_AVAILABLE:
            try:
                self._hypothesis_tracker = HypothesisTracker()
                self._hypothesis_tracker.generate_hypotheses(
                    task_goal=state.objective(),
                    evidence_pool=list(state.evidence_pool),
                    num_hypotheses=3,
                )
            except Exception as exc:
                logger.debug("brain.hypothesis_tracker_init failed: %s", exc)
                self._hypothesis_tracker = None

    def _allowed_tool_ids(self) -> set[str]:
        raw = getattr(self.state, "_allowed_tool_ids", None)
        if not isinstance(raw, (list, set, tuple)):
            allowed: set[str] = set()
        else:
            allowed = {str(tool_id).strip() for tool_id in raw if str(tool_id).strip()}
        if not self._suppress_live_inspection_expansion():
            return allowed
        return {
            tool_id
            for tool_id in allowed
            if tool_id not in {"browser.playwright.inspect", "documents.highlight.extract"}
        }

    def _runtime_settings(self) -> dict[str, Any]:
        ctx = getattr(self.state, "execution_context", None)
        settings = getattr(ctx, "settings", None)
        return settings if isinstance(settings, dict) else {}

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _suppress_live_inspection_expansion(self) -> bool:
        settings = self._runtime_settings()
        if not settings:
            return False
        depth_tier = " ".join(
            str(settings.get("__research_depth_tier") or "").split()
        ).strip().lower() or "standard"
        if depth_tier != "standard":
            return False
        target_url = " ".join(
            str(settings.get("__task_target_url") or "").split()
        ).strip()
        explicit_file_scope = any(
            self._truthy(settings.get(key))
            for key in (
                "__deep_search_prompt_scoped_pdfs",
                "__deep_search_user_selected_files",
                "__selected_file_ids",
            )
        )
        web_only = self._truthy(settings.get("__research_web_only"))
        online_research = (
            " ".join(str(settings.get("__web_routing_mode") or "").split()).strip().lower()
            == "online_research"
        )
        return (web_only or online_research) and not target_url and not explicit_file_scope

    def _filter_injected_steps(self, steps: list[Any]) -> list[Any]:
        allowed = self._allowed_tool_ids()
        suppress_live_inspection = self._suppress_live_inspection_expansion()
        if not allowed and not suppress_live_inspection:
            return list(steps)
        filtered: list[Any] = []
        for step in steps:
            tool_id = ""
            if isinstance(step, PlannedStep):
                tool_id = str(step.tool_id or "").strip()
            elif isinstance(step, dict):
                tool_id = str(step.get("tool_id") or "").strip()
            if suppress_live_inspection and tool_id in {"browser.playwright.inspect", "documents.highlight.extract"}:
                continue
            if tool_id and tool_id in allowed:
                filtered.append(step)
            elif not allowed and tool_id:
                filtered.append(step)
        return filtered

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

        # 0a. Record episode in semantic memory (non-blocking)
        try:
            _get_semantic_memory().store_episode(
                run_id=self.state.turn_id,
                agent_id=self.state.user_id,
                tenant_id=getattr(self.state, "tenant_id", ""),
                step_index=outcome.step_index,
                tool_id=outcome.tool_id,
                params_summary=str(outcome.metadata)[:500],
                outcome_status=outcome.status,
                evidence_summary=outcome.content_summary[:1000],
                duration_ms=outcome.duration_ms,
                tokens_used=outcome.metadata.get("tokens_used", 0) if isinstance(outcome.metadata, dict) else 0,
            )
        except Exception as exc:
            logger.debug("brain.semantic_memory_store failed: %s", exc)

        # 0b. Record outcome in tool pattern DB (non-blocking)
        try:
            from api.services.agent.memory.tool_patterns import hash_params
            _get_tool_pattern_db().record_outcome(
                tool_id=outcome.tool_id,
                params_hash=hash_params(outcome.metadata if isinstance(outcome.metadata, dict) else {}),
                outcome_status=outcome.status,
                error_type=outcome.error_message[:200] if outcome.error_message else "",
                context_tags=[outcome.owner_role, self.state.user_message[:50]],
                agent_id=self.state.user_id,
                tenant_id=getattr(self.state, "tenant_id", ""),
                duration_ms=outcome.duration_ms,
            )
        except Exception as exc:
            logger.debug("brain.tool_pattern_record failed: %s", exc)

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

        # 2b. Strategy stuckness detection (Innovation #10)
        # After 3+ consecutive failures or evidence plateau, check stuckness.
        try:
            if _STRATEGY_DETECTOR_AVAILABLE:
                _step_history_dicts = [
                    {
                        "tool_id": o.tool_id,
                        "status": o.status,
                        "summary": o.content_summary[:200],
                        "evidence_count": o.evidence_count,
                        "params": o.metadata.get("params", {}),
                    }
                    for o in self.state.step_outcomes
                ]
                _consecutive_fails = 0
                for _o in reversed(self.state.step_outcomes):
                    if _o.status in ("failed", "blocked", "empty"):
                        _consecutive_fails += 1
                    else:
                        break

                if _consecutive_fails >= 3 or len(self.state.step_outcomes) >= 3:
                    _detector = StrategyDetector()
                    _stuck_report = _detector.detect_stuckness(
                        step_history=_step_history_dicts,
                        evidence_pool=list(self.state.evidence_pool),
                    )
                    if _stuck_report.is_stuck:
                        _available_tool_ids = list(
                            {s.tool_id for s in steps}
                        )
                        _pivot = _detector.suggest_strategy_pivot(
                            current_strategy=self.state.gap_summary()[:200],
                            stuck_report=_stuck_report,
                            available_tools=_available_tool_ids,
                        )
                        pivot_event = activity_event_factory(
                            event_type="brain_strategy_pivot",
                            title=f"Strategy pivot: {_stuck_report.stuck_type}",
                            detail=_pivot.new_approach[:200] or _stuck_report.suggested_pivot[:200],
                            metadata={
                                "stuck_type": _stuck_report.stuck_type,
                                "consecutive_failures": _stuck_report.consecutive_failures,
                                "evidence_plateau": _stuck_report.evidence_plateau,
                                "new_approach": _pivot.new_approach[:200],
                                "rationale": _pivot.rationale[:200],
                                "pivot_step_count": len(_pivot.new_steps),
                            },
                        )
                        yield emit_event(pivot_event)

                        # Inject pivot steps into the plan
                        for _ps in self._filter_injected_steps(_pivot.new_steps[:3]):
                            if isinstance(_ps, dict) and _ps.get("tool_id"):
                                steps.append(PlannedStep(
                                    tool_id=str(_ps.get("tool_id", "")),
                                    title=str(_ps.get("title", ""))[:120],
                                    params=_ps.get("params") or {},
                                    why_this_step=str(_ps.get("why_this_step", ""))[:200],
                                    expected_evidence=(),
                                ))
        except Exception:
            pass  # Strategy detection is non-blocking.

        # 2c. Multi-hypothesis update (Innovation #2)
        try:
            if self._hypothesis_tracker is not None and outcome.content_summary.strip():
                _prev_leader = self._hypothesis_tracker.get_leading_hypothesis()
                _prev_leader_id = _prev_leader.id if _prev_leader else None

                self._hypothesis_tracker.update_all_hypotheses(
                    new_evidence=outcome.content_summary[:600],
                )

                _new_leader = self._hypothesis_tracker.get_leading_hypothesis()
                # Emit event if leading hypothesis changed
                if _new_leader and _prev_leader_id and _new_leader.id != _prev_leader_id:
                    hyp_event = activity_event_factory(
                        event_type="brain_hypothesis_shift",
                        title="Leading hypothesis changed",
                        detail=f"New lead: {_new_leader.statement[:150]} (conf={_new_leader.confidence:.2f})",
                        metadata={
                            "new_leader_id": _new_leader.id,
                            "new_leader_statement": _new_leader.statement[:200],
                            "new_leader_confidence": round(_new_leader.confidence, 3),
                            "previous_leader_id": _prev_leader_id,
                            "hypothesis_count": len(self._hypothesis_tracker.hypotheses),
                        },
                    )
                    yield emit_event(hyp_event)

                # Prune dead-end hypotheses
                _pruned = self._hypothesis_tracker.prune_hypotheses()
                if _pruned:
                    prune_event = activity_event_factory(
                        event_type="brain_hypothesis_pruned",
                        title=f"Pruned {len(_pruned)} dead-end hypothesis(es)",
                        detail="; ".join(h.statement[:80] for h in _pruned[:3]),
                        metadata={
                            "pruned_count": len(_pruned),
                            "remaining_count": len(self._hypothesis_tracker.hypotheses),
                        },
                    )
                    yield emit_event(prune_event)

                # If all hypotheses abandoned, trigger plan revision signal
                if not self._hypothesis_tracker.hypotheses:
                    abandon_event = activity_event_factory(
                        event_type="brain_hypothesis_exhausted",
                        title="All hypotheses abandoned",
                        detail="No viable hypotheses remain — triggering plan revision.",
                        metadata={"trigger": "hypothesis_exhaustion"},
                    )
                    yield emit_event(abandon_event)
        except Exception:
            pass  # Hypothesis tracking is non-blocking.

        # 2d. Causal DAG impact analysis (Innovation #4)
        # If a step failed, predict which downstream steps are affected and
        # optionally suggest bypass alternatives.
        try:
            if outcome.status in ("failed", "blocked"):
                _causal = _get_causal_dag()
                _causal_graph = getattr(self.state, "_causal_graph", None)
                if _causal is not None and _causal_graph is not None:
                    _failed_step_id = f"step_{outcome.step_index}"
                    _affected = _causal.predict_impact(_causal_graph, _failed_step_id)
                    if _affected:
                        impact_event = activity_event_factory(
                            event_type="causal_dag_impact",
                            title=f"Failure impact: {len(_affected)} downstream step(s) affected",
                            detail=f"Step {outcome.step_index} ({outcome.tool_id}) failed → affects: {', '.join(_affected[:5])}",
                            metadata={
                                "failed_step_id": _failed_step_id,
                                "affected_steps": _affected[:10],
                                "tool_id": outcome.tool_id,
                            },
                        )
                        yield emit_event(impact_event)

                        # Try to suggest bypass alternatives
                        _available_tools: list[str] = []
                        try:
                            if hasattr(self.registry, "list_tool_ids"):
                                _available_tools = list(self.registry.list_tool_ids())[:40]
                            elif hasattr(self.registry, "tools"):
                                _available_tools = [
                                    t.tool_id for t in list(self.registry.tools.values())[:40]
                                ]
                        except Exception:
                            pass
                        if _available_tools:
                            _bypass = _causal.suggest_bypass(
                                _causal_graph, _failed_step_id, _available_tools,
                            )
                            if _bypass:
                                bypass_event = activity_event_factory(
                                    event_type="causal_dag_bypass",
                                    title=f"Bypass suggestion: {len(_bypass)} alternative(s)",
                                    detail=str(_bypass[0].get("rationale", ""))[:200] if _bypass else "",
                                    metadata={"alternatives": _bypass[:3]},
                                )
                                yield emit_event(bypass_event)
        except Exception:
            pass  # Causal DAG impact analysis is non-blocking.

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
            # --- Prospective Reasoning (Innovation #1) ---
            # Before continuing, estimate success of the next step.
            # If probability is too low, suggest an alternative.
            try:
                prospective = _get_prospective_reasoner()
                if prospective is not None:
                    next_step_idx = len(self.state.step_outcomes)
                    if next_step_idx < len(steps):
                        next_step = steps[next_step_idx]
                        step_dict = {
                            "tool_id": next_step.tool_id,
                            "title": next_step.title,
                            "params": next_step.params,
                            "why_this_step": next_step.why_this_step,
                        }
                        tool_history = [
                            {
                                "tool_id": o.tool_id,
                                "status": o.status,
                                "content_summary": o.content_summary[:200],
                                "error_message": o.error_message[:120],
                            }
                            for o in self.state.step_outcomes[-10:]
                        ]
                        forecast = prospective.estimate_step_success(
                            step=step_dict,
                            evidence_pool=list(self.state.evidence_pool),
                            tool_history=tool_history,
                        )
                        # Store forecast in state metadata for UI visibility.
                        if not hasattr(self.state, "_reasoning_metadata"):
                            self.state._reasoning_metadata = {}
                        self.state._reasoning_metadata["last_forecast"] = {
                            "tool_id": forecast.tool_id,
                            "probability": forecast.estimated_success_probability,
                            "reasoning": forecast.reasoning[:200],
                            "risk_factors": forecast.risk_factors[:4],
                        }

                        if not prospective.should_proceed(forecast, min_probability=0.4):
                            # Try to suggest a better alternative.
                            available_tools: list[str] = []
                            try:
                                if hasattr(self.registry, "list_tool_ids"):
                                    available_tools = list(self.registry.list_tool_ids())[:40]
                                elif hasattr(self.registry, "tools"):
                                    available_tools = [
                                        t.tool_id
                                        for t in list(self.registry.tools.values())[:40]
                                    ]
                            except Exception:
                                pass

                            if available_tools:
                                alt = prospective.suggest_alternative(
                                    forecast=forecast,
                                    available_tools=available_tools,
                                    evidence_pool=list(self.state.evidence_pool),
                                    tool_history=tool_history,
                                )
                                if alt and alt.get("tool_id"):
                                    reason = (
                                        f"Prospective reasoning: {next_step.tool_id} "
                                        f"predicted {forecast.estimated_success_probability:.0%} "
                                        f"success. Replacing with {alt['tool_id']}. "
                                        f"{forecast.reasoning[:100]}"
                                    )
                                    return BrainDirective(
                                        action="add_steps",
                                        injected_steps=[alt],
                                        directive_reason=reason,
                                    )
            except Exception as exc:
                logger.debug("brain.prospective_reasoning_failed error=%s", exc)

            # --- Tool Composition (Innovation #9) ---
            # Before continuing, check if the next step would benefit from
            # decomposition into a multi-tool chain.
            try:
                composer = _get_tool_composer()
                if composer is not None:
                    next_step_idx = len(self.state.step_outcomes)
                    if next_step_idx < len(steps):
                        _next = steps[next_step_idx]
                        _step_dict = {
                            "tool_id": _next.tool_id,
                            "title": _next.title,
                            "params": _next.params,
                            "why_this_step": _next.why_this_step,
                        }
                        _avail_tools: list[str] = []
                        try:
                            if hasattr(self.registry, "list_tool_ids"):
                                _avail_tools = list(self.registry.list_tool_ids())[:40]
                            elif hasattr(self.registry, "tools"):
                                _avail_tools = [
                                    t.tool_id for t in list(self.registry.tools.values())[:40]
                                ]
                        except Exception:
                            pass
                        if _avail_tools:
                            allowed = self._allowed_tool_ids()
                            if allowed:
                                _avail_tools = [tool_id for tool_id in _avail_tools if tool_id in allowed]
                        if _avail_tools:
                            if (
                                self._suppress_live_inspection_expansion()
                                and _next.tool_id in {"marketing.web_research", "web.extract.structured"}
                            ):
                                _avail_tools = []
                        if _avail_tools:
                            _plan = composer.detect_composition_opportunity(
                                step=_step_dict,
                                available_tools=_avail_tools,
                                evidence_pool=list(self.state.evidence_pool),
                            )
                            if _plan and len(_plan.steps) >= 2:
                                reason = (
                                    f"Tool composition: decomposing {_next.tool_id} "
                                    f"into {len(_plan.steps)}-step chain. "
                                    f"{_plan.rationale[:120]}"
                                )
                                return BrainDirective(
                                    action="add_steps",
                                    injected_steps=_plan.steps,
                                    directive_reason=reason,
                                )
            except Exception as exc:
                logger.debug("brain.tool_composer_failed error=%s", exc)

            return BrainDirective(
                action="continue",
                directive_reason=f"{remaining} planned step(s) remaining.",
            )

        # No more planned steps — try to revise if budget allows.
        if self.state.can_revise():
            new_steps = build_revision_steps(
                state=self.state,
                registry=self.registry,
                allowed_tool_ids=self._allowed_tool_ids(),
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
