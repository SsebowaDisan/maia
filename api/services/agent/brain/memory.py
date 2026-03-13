"""Cross-turn Brain memory via SessionPool.extra.

The Brain accumulates evidence and coverage state within a single turn.
Between turns, we persist a compact summary in ``AgentSession.extra``
so the next turn's Brain can:
  - Skip re-fetching evidence that was already found
  - Understand what the agent tried previously (and what failed)
  - Carry forward successful fact coverage across multi-turn conversations

All persistence is best-effort — failures are silently logged so the
main execution path is never blocked.

Environment
-----------
MAIA_BRAIN_MEMORY_ENABLED   (default "true") — set "false" to disable
                             cross-turn persistence entirely.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from api.services.agent.session_pool import SessionPool

from .state import BrainState

logger = logging.getLogger(__name__)

_ENABLED = os.environ.get("MAIA_BRAIN_MEMORY_ENABLED", "true").lower() != "false"
_MEMORY_KEY = "brain_memory"
_MAX_EVIDENCE_ITEMS = 12
_MAX_COVERED_FACTS = 30


def save_brain_memory(state: BrainState) -> None:
    """Persist a compact summary of this turn's Brain state.

    Called at the end of run_stream(), after execute_planned_steps completes.
    """
    if not _ENABLED:
        return
    try:
        session = SessionPool.acquire(state.user_id, state.conversation_id)
        memory = session.extra.setdefault(_MEMORY_KEY, {})

        # Accumulate covered facts (de-dup across turns).
        prior_facts: dict[str, bool] = memory.get("covered_facts", {})
        for fact, covered in state.fact_coverage.covered.items():
            if covered:
                prior_facts[fact[:200]] = True
        if len(prior_facts) > _MAX_COVERED_FACTS:
            # Keep the most recently added (last N).
            keys = list(prior_facts.keys())
            prior_facts = {k: True for k in keys[-_MAX_COVERED_FACTS:]}
        memory["covered_facts"] = prior_facts

        # Accumulate evidence summaries.
        prior_evidence: list[str] = memory.get("evidence_pool", [])
        prior_evidence.extend(state.evidence_pool)
        memory["evidence_pool"] = prior_evidence[-_MAX_EVIDENCE_ITEMS:]

        # Record which tools ran and their statuses.
        tool_history: list[dict[str, Any]] = memory.get("tool_history", [])
        for o in state.step_outcomes:
            tool_history.append({
                "tool_id": o.tool_id,
                "status": o.status,
                "summary": o.content_summary[:120],
            })
        memory["tool_history"] = tool_history[-20:]

        # Record halt reason for next turn's context.
        if state.halt_reason:
            memory["last_halt_reason"] = state.halt_reason

        session.extra[_MEMORY_KEY] = memory
        SessionPool.release(state.user_id, state.conversation_id)
        logger.debug(
            "brain.memory.saved user=%s conv=%s facts=%d evidence=%d",
            state.user_id,
            state.conversation_id,
            len(prior_facts),
            len(memory["evidence_pool"]),
        )
    except Exception as exc:
        logger.debug("brain.memory.save_failed error=%s", exc)


def load_brain_memory(
    *,
    user_id: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Load the prior-turn Brain memory for this conversation.

    Returns an empty dict if nothing is stored or memory is disabled.
    The dict may contain:
      - ``covered_facts``: {fact_str: True} already satisfied in past turns
      - ``evidence_pool``: list of "[tool_id] summary" strings
      - ``tool_history``: list of {tool_id, status, summary}
      - ``last_halt_reason``: str
    """
    if not _ENABLED:
        return {}
    try:
        session = SessionPool.acquire(user_id, conversation_id)
        memory = dict(session.extra.get(_MEMORY_KEY, {}))
        SessionPool.release(user_id, conversation_id)
        return memory
    except Exception as exc:
        logger.debug("brain.memory.load_failed error=%s", exc)
        return {}


def apply_memory_to_state(state: BrainState, memory: dict[str, Any]) -> None:
    """Pre-populate BrainState with facts already known from prior turns.

    Facts that were covered in past turns are marked covered immediately so
    the Brain does not waste steps re-fetching them.
    Prior evidence is injected into the evidence pool so the discussion /
    reviser LLMs have full context.
    """
    if not memory:
        return

    covered_facts: dict[str, bool] = memory.get("covered_facts", {})
    for fact in state.fact_coverage.required_facts:
        if covered_facts.get(fact):
            state.fact_coverage.mark_covered(fact, "prior_turn_memory")

    prior_evidence: list[str] = memory.get("evidence_pool", [])
    for item in prior_evidence[-6:]:
        if item not in state.evidence_pool:
            state.evidence_pool.insert(0, f"[memory] {item}")

    logger.debug(
        "brain.memory.applied pre_covered=%d prior_evidence=%d",
        sum(1 for f in state.fact_coverage.required_facts
            if state.fact_coverage.covered.get(f)),
        len(prior_evidence),
    )
