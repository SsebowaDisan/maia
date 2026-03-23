"""LLM-driven adaptive plan reviser.

When the Brain detects uncovered facts after a step, the reviser asks
the LLM to propose 1-3 new PlannedStep dicts.  No hardcoded logic —
the LLM sees the full context (user goal, executed tools, evidence,
remaining gaps, available tool IDs) and decides what to do next.

Returned steps are appended to the live `steps` list by Brain.assess()
when directive == "add_steps".

Environment
-----------
MAIA_BRAIN_REVISER_MAX_STEPS   (default "3") — maximum new steps per revision
"""
from __future__ import annotations

import logging
import os
from typing import Any

from api.services.agent.llm_runtime import call_json_response
from api.services.agent.planner_models import PlannedStep

from .state import BrainState

logger = logging.getLogger(__name__)

_MAX_NEW_STEPS = int(os.environ.get("MAIA_BRAIN_REVISER_MAX_STEPS", "3"))

_SYSTEM_PROMPT = """\
You are a strategic plan reviser for an AI agent.
Your job is to propose a minimal set of new tool steps that will fill the
remaining gaps in the task contract.

Rules:
- Only propose steps that directly address a missing fact or incomplete action
- Reuse tool IDs that were already successful before adding new ones
- Never propose more than {max_steps} new steps
- Do not repeat a tool + params combination that already failed
- Return ONLY valid JSON — no prose, no markdown
"""

_USER_TEMPLATE = """\
USER GOAL: {user_goal}

AGENT OBJECTIVE: {objective}

STEPS ALREADY EXECUTED:
{executed_steps}

EVIDENCE COLLECTED SO FAR:
{evidence_summary}

STILL MISSING:
{gap_summary}

AVAILABLE TOOL IDs:
{available_tools}

Propose 1-{max_steps} new steps to fill the remaining gaps.

Return JSON array:
[
  {{
    "tool_id": "<tool_id>",
    "title": "<short human-readable title>",
    "params": {{}},
    "why_this_step": "<one sentence connecting this step to the missing fact>",
    "expected_evidence": ["<what this step should find>"]
  }}
]

If no additional steps are needed, return an empty array: []
"""


def _format_executed_steps(state: BrainState) -> str:
    if not state.step_outcomes:
        return "  (none)"
    lines = []
    for i, o in enumerate(state.step_outcomes, 1):
        lines.append(f"  {i}. [{o.status}] {o.tool_id} — {o.content_summary[:120]}")
    return "\n".join(lines)


def _format_available_tools(registry: Any) -> str:
    """Extract tool IDs from the tool registry."""
    try:
        if hasattr(registry, "list_tool_ids"):
            ids = list(registry.list_tool_ids())[:40]
        elif hasattr(registry, "tools"):
            ids = [t.tool_id for t in list(registry.tools.values())[:40]]
        else:
            return "  (unavailable)"
        return "  " + ", ".join(ids)
    except Exception:
        return "  (unavailable)"


def _normalize_allowed_tool_ids(allowed_tool_ids: list[str] | set[str] | tuple[str, ...] | None) -> list[str]:
    if not allowed_tool_ids:
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for tool_id in allowed_tool_ids:
        normalized = str(tool_id).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def build_revision_steps(
    *,
    state: BrainState,
    registry: Any,
    allowed_tool_ids: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[PlannedStep]:
    """Ask the LLM to propose new PlannedSteps to cover remaining gaps.

    Returns an empty list on failure or when no steps are needed.
    The caller (Brain.assess) decides whether to actually inject them.
    """
    gap = state.gap_summary()
    if gap == "No specific gaps identified.":
        return []

    effective_allowed_tool_ids = _normalize_allowed_tool_ids(allowed_tool_ids)
    system = _SYSTEM_PROMPT.format(max_steps=_MAX_NEW_STEPS)
    prompt = _USER_TEMPLATE.format(
        user_goal=state.user_message[:300],
        objective=state.objective(),
        executed_steps=_format_executed_steps(state),
        evidence_summary=state.evidence_summary()[:500],
        gap_summary=gap[:300],
        available_tools=(
            "  " + ", ".join(effective_allowed_tool_ids)
            if effective_allowed_tool_ids
            else _format_available_tools(registry)
        ),
        max_steps=_MAX_NEW_STEPS,
    )

    try:
        raw = call_json_response(
            system_prompt=system,
            user_prompt=prompt,
            temperature=0.2,
            timeout_seconds=16,
        )
    except Exception as exc:
        logger.debug("brain.reviser.llm_failed error=%s", exc)
        return []

    if not isinstance(raw, list):
        logger.debug("brain.reviser.non_list_response type=%s", type(raw).__name__)
        return []

    steps: list[PlannedStep] = []
    for item in raw[:_MAX_NEW_STEPS]:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id", "")).strip()
        title = str(item.get("title", "")).strip()
        if not tool_id or not title:
            logger.debug("brain.reviser.skipping_item missing tool_id or title")
            continue
        if effective_allowed_tool_ids and tool_id not in effective_allowed_tool_ids:
            logger.debug(
                "brain.reviser.skipping_item disallowed_tool tool_id=%s",
                tool_id,
            )
            continue
        params = item.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        why = str(item.get("why_this_step", ""))[:200]
        evidence_raw = item.get("expected_evidence") or []
        if isinstance(evidence_raw, list):
            expected_evidence = tuple(str(e) for e in evidence_raw[:4])
        else:
            expected_evidence = ()
        steps.append(PlannedStep(
            tool_id=tool_id,
            title=title[:120],
            params=params,
            why_this_step=why,
            expected_evidence=expected_evidence,
        ))

    logger.debug("brain.reviser.proposed_steps count=%d", len(steps))
    return steps
