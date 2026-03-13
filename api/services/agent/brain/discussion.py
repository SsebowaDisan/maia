"""LLM inner-monologue — Brain's reasoning attached to every step.

Before the Brain decides what to do next, it generates a short
"thought" that:
  1. Re-anchors to the user's original question
  2. Summarises what the current step found (or didn't)
  3. States what is still missing
  4. Explains the next move (continue / revise / halt) in plain language

This thought is:
  - Returned as ``BrainDirective.brain_thought``
  - Emitted as a ``brain_thinking`` activity event (visible in the agent panel)

The prompt is fully LLM-driven.  No hardcoded keywords or decision trees.

Environment
-----------
MAIA_BRAIN_DISCUSSION_ENABLED  (default "true")  — set "false" to skip
                                 the inner-monologue step entirely.
"""
from __future__ import annotations

import logging
import os

from api.services.agent.llm_runtime import call_text_response

from .state import BrainState
from .signals import StepOutcome

logger = logging.getLogger(__name__)

_ENABLED = os.environ.get("MAIA_BRAIN_DISCUSSION_ENABLED", "true").lower() != "false"

_SYSTEM_PROMPT = """\
You are the strategic reasoning brain of an AI agent.
After each tool step, you think aloud in 3-4 sentences to make sure the
agent stays aligned with the user's goal.

Your thinking must:
- Start by restating what the user actually wants (in your own words)
- State what the current step found or failed to find
- Identify what is still missing (if anything)
- Conclude with the clearest next move

Be concise, direct, and specific to the user's task.
Do not use bullet points. Write as flowing sentences.
"""

_USER_TEMPLATE = """\
USER MESSAGE: {user_message}

OBJECTIVE: {objective}

STEP JUST COMPLETED ({step_index}/{total_steps}):
  Tool: {tool_id}
  Title: {step_title}
  Status: {status}
  Found: {content_summary}

CONTRACT COVERAGE SO FAR:
  Facts covered: {facts_covered}/{total_facts}
  Actions completed: {actions_completed}/{total_actions}

STILL MISSING:
  {gap_summary}

EVIDENCE COLLECTED:
  {evidence_summary}

REVISION BUDGET REMAINING: {revisions_remaining}

Think through what the agent should do next.
"""

_RATIONALE_SYSTEM = """\
You are a planning assistant. Generate a concise rationale (2-3 sentences)
explaining how a planned step advances the user's goal.
Be specific — name what evidence the step is expected to find.
"""

_RATIONALE_TEMPLATE = """\
USER GOAL: {user_goal}
AGENT OBJECTIVE: {objective}
STEP {step_index}/{total_steps}: {step_title}
TOOL: {tool_id}
WHY PLANNED: {why_this_step}
EXPECTED EVIDENCE: {expected_evidence}

In 2-3 sentences, explain how this step helps answer the user's question.
"""


def generate_step_thought(
    *,
    state: BrainState,
    outcome: StepOutcome,
    step_title: str,
    total_steps: int,
    revisions_remaining: int,
) -> str:
    """Generate the Brain's inner-monologue after a step completes.

    Returns a plain-text thought string (empty string on failure).
    Called by Brain.assess() before making a directive decision.
    """
    if not _ENABLED:
        return ""

    fact_cov = state.fact_coverage
    action_cov = state.action_coverage
    facts_covered = sum(1 for f in fact_cov.required_facts if fact_cov.covered.get(f))
    total_facts = len(fact_cov.required_facts)
    actions_done = sum(1 for a in action_cov.required_actions if action_cov.completed.get(a))
    total_actions = len(action_cov.required_actions)

    prompt = _USER_TEMPLATE.format(
        user_message=state.user_message[:400],
        objective=state.objective(),
        step_index=len(state.step_outcomes),
        total_steps=total_steps,
        tool_id=outcome.tool_id,
        step_title=step_title[:120],
        status=outcome.status,
        content_summary=outcome.content_summary[:400] or "(nothing returned)",
        facts_covered=facts_covered,
        total_facts=total_facts or "N/A",
        actions_completed=actions_done,
        total_actions=total_actions or "N/A",
        gap_summary=state.gap_summary()[:300],
        evidence_summary=state.evidence_summary()[:400],
        revisions_remaining=revisions_remaining,
    )
    try:
        thought = call_text_response(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.3,
            timeout_seconds=14,
            max_tokens=200,
        )
        return thought.strip()
    except Exception as exc:
        logger.debug("brain.discussion.thought_failed error=%s", exc)
        return ""


def generate_step_rationale(
    *,
    state: BrainState,
    step_index: int,
    total_steps: int,
    tool_id: str,
    step_title: str,
    why_this_step: str,
    expected_evidence: list[str] | tuple[str, ...],
) -> str:
    """Generate a forward-looking rationale before a step runs.

    This is emitted BEFORE the step executes so the user sees why
    the agent is about to do something.  Returns plain text.
    """
    if not _ENABLED:
        return why_this_step

    prompt = _RATIONALE_TEMPLATE.format(
        user_goal=state.user_message[:300],
        objective=state.objective(),
        step_index=step_index,
        total_steps=total_steps,
        step_title=step_title[:120],
        tool_id=tool_id,
        why_this_step=why_this_step[:200] or "Not specified.",
        expected_evidence=", ".join(list(expected_evidence)[:4]) or "Not specified.",
    )
    try:
        rationale = call_text_response(
            system_prompt=_RATIONALE_SYSTEM,
            user_prompt=prompt,
            temperature=0.2,
            timeout_seconds=10,
            max_tokens=120,
        )
        return rationale.strip() or why_this_step
    except Exception as exc:
        logger.debug("brain.discussion.rationale_failed error=%s", exc)
        return why_this_step
