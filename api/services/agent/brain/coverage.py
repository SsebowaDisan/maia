"""LLM-based semantic contract coverage checker.

After each tool step, asks the LLM whether the tool's output satisfies
each uncovered required_fact in the task contract.

No keyword lists.  No regex matching.  Purely semantic — the LLM reads
the tool output and the fact, and decides.

Environment
-----------
MAIA_BRAIN_LLM_COVERAGE_CHECK   (default "true")  — set "false" to skip
                                  LLM coverage and mark facts covered only
                                  when the Brain explicitly asserts them.
MAIA_BRAIN_COVERAGE_CONFIDENCE  (default "0.65")  — minimum LLM confidence
                                  to count a fact as covered.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from api.services.agent.llm_runtime import call_json_response

from .state import BrainState
from .signals import StepOutcome

logger = logging.getLogger(__name__)

_COVERAGE_ENABLED = os.environ.get("MAIA_BRAIN_LLM_COVERAGE_CHECK", "true").lower() != "false"
_MIN_CONFIDENCE = float(os.environ.get("MAIA_BRAIN_COVERAGE_CONFIDENCE", "0.65"))

_SYSTEM_PROMPT = (
    "You are a contract-coverage analyst for an AI agent. "
    "Your job is to determine whether a tool's output satisfies a specific "
    "required fact from the task contract. "
    "Be strict: partial information does not count as satisfied. "
    "Return ONLY valid JSON — no prose, no markdown."
)

_USER_TEMPLATE = """\
USER GOAL: {user_goal}

TASK OBJECTIVE: {objective}

REQUIRED FACT TO CHECK:
  {required_fact}

TOOL THAT JUST RAN: {tool_id}
TOOL OUTPUT SUMMARY:
  {content_summary}

Does this tool output satisfy the required fact?

Return JSON:
{{
  "satisfied": <true or false>,
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence why>"
}}
"""

_ACTION_SYSTEM_PROMPT = (
    "You are a contract-action analyst for an AI agent. "
    "Determine whether a tool's execution completed a required action. "
    "Return ONLY valid JSON."
)

_ACTION_USER_TEMPLATE = """\
USER GOAL: {user_goal}

REQUIRED ACTION: {required_action}

TOOL THAT JUST RAN: {tool_id}
TOOL OUTPUT SUMMARY:
  {content_summary}

Did this tool execution complete the required action?

Return JSON:
{{
  "completed": <true or false>,
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence why>"
}}
"""


def _check_fact(
    *,
    required_fact: str,
    outcome: StepOutcome,
    state: BrainState,
) -> tuple[bool, float, str]:
    """Ask the LLM if this outcome satisfies a required fact.

    Returns (satisfied, confidence, reason).
    """
    if not outcome.content_summary.strip():
        return False, 0.0, "Tool produced no output."

    prompt = _USER_TEMPLATE.format(
        user_goal=state.user_message[:300],
        objective=state.objective(),
        required_fact=required_fact[:300],
        tool_id=outcome.tool_id,
        content_summary=outcome.content_summary[:1400],
    )
    try:
        raw = call_json_response(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.0,
            timeout_seconds=12,
        )
        if not isinstance(raw, dict):
            return False, 0.0, "LLM returned non-dict."
        satisfied = bool(raw.get("satisfied", False))
        confidence = float(raw.get("confidence", 0.0))
        reason = str(raw.get("reason", ""))[:200]
        return satisfied, confidence, reason
    except Exception as exc:
        logger.debug("brain.coverage.fact_check_failed fact=%r error=%s", required_fact[:60], exc)
        return False, 0.0, str(exc)[:100]


def _check_action(
    *,
    required_action: str,
    outcome: StepOutcome,
    state: BrainState,
) -> tuple[bool, float, str]:
    """Ask the LLM if this outcome completed a required action."""
    if not outcome.content_summary.strip():
        return False, 0.0, "Tool produced no output."

    prompt = _ACTION_USER_TEMPLATE.format(
        user_goal=state.user_message[:300],
        required_action=required_action[:200],
        tool_id=outcome.tool_id,
        content_summary=outcome.content_summary[:1200],
    )
    try:
        raw = call_json_response(
            system_prompt=_ACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.0,
            timeout_seconds=12,
        )
        if not isinstance(raw, dict):
            return False, 0.0, "LLM returned non-dict."
        completed = bool(raw.get("completed", False))
        confidence = float(raw.get("confidence", 0.0))
        reason = str(raw.get("reason", ""))[:200]
        return completed, confidence, reason
    except Exception as exc:
        logger.debug("brain.coverage.action_check_failed action=%r error=%s", required_action[:60], exc)
        return False, 0.0, str(exc)[:100]


def update_coverage(state: BrainState, outcome: StepOutcome) -> list[dict[str, Any]]:
    """Check this outcome against all uncovered facts and actions.

    Mutates state.fact_coverage and state.action_coverage in-place.

    Returns a list of coverage events suitable for emitting:
    [{"fact": ..., "satisfied": ..., "confidence": ..., "reason": ...}, ...]
    """
    if not _COVERAGE_ENABLED:
        return []

    # Skip coverage if the step failed with no content.
    if outcome.status == "failed" and not outcome.content_summary.strip():
        return []

    events: list[dict[str, Any]] = []

    for fact in state.fact_coverage.uncovered_facts():
        satisfied, confidence, reason = _check_fact(
            required_fact=fact,
            outcome=outcome,
            state=state,
        )
        logger.debug(
            "brain.coverage.fact fact=%r satisfied=%s confidence=%.2f",
            fact[:60], satisfied, confidence,
        )
        if satisfied and confidence >= _MIN_CONFIDENCE:
            state.fact_coverage.mark_covered(fact, outcome.tool_id)
            events.append({
                "type": "fact_covered",
                "fact": fact,
                "confidence": confidence,
                "reason": reason,
                "tool_id": outcome.tool_id,
            })

    for action in state.action_coverage.uncompleted_actions():
        completed, confidence, reason = _check_action(
            required_action=action,
            outcome=outcome,
            state=state,
        )
        logger.debug(
            "brain.coverage.action action=%r completed=%s confidence=%.2f",
            action[:60], completed, confidence,
        )
        if completed and confidence >= _MIN_CONFIDENCE:
            state.action_coverage.mark_completed(action)
            events.append({
                "type": "action_completed",
                "action": action,
                "confidence": confidence,
                "reason": reason,
                "tool_id": outcome.tool_id,
            })

    return events
