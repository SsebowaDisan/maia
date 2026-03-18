"""Explicit chain-of-thought reasoning before and after tool calls.

Forces the agent to articulate structured thinking before executing a step
and provides structured failure analysis after errors.  All reasoning chains
are visible to users via brain_thinking events.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReasoningChain:
    """Output of pre-action chain-of-thought reasoning."""
    thoughts: list[str] = field(default_factory=list)
    conclusion: str = ""
    confidence: float = 0.7
    should_modify_params: bool = False
    modified_params: dict[str, Any] | None = None


@dataclass(frozen=True)
class RecoveryReasoning:
    """Output of post-failure structured analysis."""
    analysis: str = ""
    root_cause: str = ""
    recovery_options: list[dict[str, Any]] = field(default_factory=list)
    recommended_action: str = ""  # retry | switch_tool | modify_params | skip | escalate


_COT_SYSTEM_PROMPT = """\
You are a reasoning engine for an AI agent.  Before the agent executes a tool
step you must think through five structured questions.  Your reasoning will
be shown to the user, so be clear and concise.

Rules:
- Return ONLY valid JSON — no prose, no markdown.
- Each thought should be 1-2 sentences max.
- confidence is a float 0.0-1.0.
- If you recommend modifying params, set should_modify_params to true and
  provide modified_params with only the changed keys.
"""

_COT_USER_TEMPLATE = """\
TASK GOAL: {task_goal}

CURRENT STEP:
  tool_id: {tool_id}
  title: {step_title}
  params: {step_params}
  why: {why_this_step}

EVIDENCE COLLECTED SO FAR:
{evidence_so_far}

REMAINING STEPS AFTER THIS: {remaining_steps}

Think through these five questions:
1. "What do I know so far?" — summarize evidence state
2. "What does this step aim to achieve?" — restate the step goal
3. "What could go wrong?" — identify risks
4. "Is this the best approach right now?" — consider alternatives
5. "Should I modify the parameters?" — concrete adjustments

Return JSON:
{{
  "thoughts": [
    "<answer to Q1>",
    "<answer to Q2>",
    "<answer to Q3>",
    "<answer to Q4>",
    "<answer to Q5>"
  ],
  "conclusion": "<one-sentence overall assessment>",
  "confidence": <float 0.0-1.0>,
  "should_modify_params": <bool>,
  "modified_params": <dict or null>
}}
"""

_RECOVERY_SYSTEM_PROMPT = """\
You are a failure analysis engine for an AI agent.  A tool step has failed.
Analyze the root cause and suggest recovery options.

Rules:
- Return ONLY valid JSON — no prose, no markdown.
- recommended_action must be one of: retry, switch_tool, modify_params, skip, escalate
- recovery_options: list of 1-3 concrete options, each with action, tool_id (if applicable), params, and rationale.
- Be practical: if the error is clearly transient (timeout, network), recommend retry.
  If the tool is wrong for the job, suggest switch_tool.
"""

_RECOVERY_USER_TEMPLATE = """\
FAILED STEP:
  tool_id: {tool_id}
  title: {step_title}
  params: {step_params}
  why: {why_this_step}

ERROR:
  {error}

EVIDENCE COLLECTED SO FAR:
{evidence_pool}

AVAILABLE TOOLS:
  {available_tools}

Analyze the failure, identify root cause, and suggest recovery options.

Return JSON:
{{
  "analysis": "<what happened and why>",
  "root_cause": "<concise root cause>",
  "recovery_options": [
    {{
      "action": "retry|switch_tool|modify_params|skip|escalate",
      "tool_id": "<tool_id or null>",
      "params": {{}},
      "rationale": "<why this option>"
    }}
  ],
  "recommended_action": "retry|switch_tool|modify_params|skip|escalate"
}}
"""


def _format_evidence(evidence: list[str]) -> str:
    if not evidence:
        return "  (no evidence collected yet)"
    return "\n".join(f"  - {e[:200]}" for e in evidence[-8:])


class ChainOfThoughtReasoner:
    """Explicit chain-of-thought reasoning before and after tool calls.

    Pre-action: forces structured thinking through five questions.
    Post-failure: structured root-cause analysis with recovery options.
    """

    def reason_before_action(
        self,
        task_goal: str,
        current_step: dict[str, Any],
        evidence_so_far: list[str],
        remaining_steps: int,
    ) -> ReasoningChain:
        """Generate chain-of-thought reasoning before executing a step.

        Parameters
        ----------
        task_goal:
            The overall task objective.
        current_step:
            Dict with tool_id, title, params, why_this_step.
        evidence_so_far:
            Evidence strings accumulated from prior steps.
        remaining_steps:
            Number of steps remaining after this one.

        Returns
        -------
        ReasoningChain with thoughts, conclusion, confidence, and
        optional parameter modifications.
        """
        import json

        tool_id = str(current_step.get("tool_id", ""))
        step_title = str(current_step.get("title", ""))
        step_params = current_step.get("params", {})
        why = str(current_step.get("why_this_step", ""))

        prompt = _COT_USER_TEMPLATE.format(
            task_goal=task_goal[:300],
            tool_id=tool_id,
            step_title=step_title[:120],
            step_params=json.dumps(step_params, default=str)[:300],
            why_this_step=why[:200],
            evidence_so_far=_format_evidence(evidence_so_far),
            remaining_steps=remaining_steps,
        )

        try:
            raw = call_json_response(
                system_prompt=_COT_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.15,
                timeout_seconds=12,
            )
        except Exception as exc:
            logger.debug("cot.reason_before_action_failed error=%s", exc)
            return ReasoningChain(
                thoughts=[f"Reasoning unavailable: {exc}"],
                conclusion="Proceeding with step as planned.",
                confidence=0.5,
            )

        if not isinstance(raw, dict):
            return ReasoningChain(
                thoughts=["LLM returned non-dict response."],
                conclusion="Proceeding with step as planned.",
                confidence=0.5,
            )

        thoughts_raw = raw.get("thoughts", [])
        if isinstance(thoughts_raw, list):
            thoughts = [str(t)[:200] for t in thoughts_raw[:5]]
        else:
            thoughts = [str(thoughts_raw)[:200]]

        conclusion = str(raw.get("conclusion", ""))[:300]

        confidence = raw.get("confidence", 0.7)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        should_modify = bool(raw.get("should_modify_params", False))
        modified = raw.get("modified_params")
        if not isinstance(modified, dict):
            modified = None
            should_modify = False

        return ReasoningChain(
            thoughts=thoughts,
            conclusion=conclusion,
            confidence=confidence,
            should_modify_params=should_modify,
            modified_params=modified,
        )

    def reason_after_failure(
        self,
        failed_step: dict[str, Any],
        error: str,
        evidence_pool: list[str],
        available_tools: list[str],
    ) -> RecoveryReasoning:
        """Generate structured failure analysis after a step fails.

        Parameters
        ----------
        failed_step:
            Dict with tool_id, title, params, why_this_step.
        error:
            The error message or traceback string.
        evidence_pool:
            Evidence accumulated so far.
        available_tools:
            List of tool IDs the agent can use.

        Returns
        -------
        RecoveryReasoning with analysis, root cause, recovery options,
        and recommended action.
        """
        import json

        tool_id = str(failed_step.get("tool_id", ""))
        step_title = str(failed_step.get("title", ""))
        step_params = failed_step.get("params", {})
        why = str(failed_step.get("why_this_step", ""))

        prompt = _RECOVERY_USER_TEMPLATE.format(
            tool_id=tool_id,
            step_title=step_title[:120],
            step_params=json.dumps(step_params, default=str)[:300],
            why_this_step=why[:200],
            error=str(error)[:400],
            evidence_pool=_format_evidence(evidence_pool),
            available_tools=", ".join(available_tools[:30]),
        )

        try:
            raw = call_json_response(
                system_prompt=_RECOVERY_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.1,
                timeout_seconds=12,
            )
        except Exception as exc:
            logger.debug("cot.reason_after_failure_failed error=%s", exc)
            return RecoveryReasoning(
                analysis=f"Recovery analysis failed: {exc}",
                root_cause="unknown",
                recovery_options=[],
                recommended_action="skip",
            )

        if not isinstance(raw, dict):
            return RecoveryReasoning(
                analysis="LLM returned non-dict response.",
                root_cause="unknown",
                recovery_options=[],
                recommended_action="skip",
            )

        analysis = str(raw.get("analysis", ""))[:500]
        root_cause = str(raw.get("root_cause", "unknown"))[:200]

        options_raw = raw.get("recovery_options", [])
        recovery_options: list[dict[str, Any]] = []
        if isinstance(options_raw, list):
            for opt in options_raw[:3]:
                if isinstance(opt, dict):
                    recovery_options.append({
                        "action": str(opt.get("action", "skip"))[:20],
                        "tool_id": str(opt.get("tool_id", ""))[:60] or None,
                        "params": opt.get("params") if isinstance(opt.get("params"), dict) else {},
                        "rationale": str(opt.get("rationale", ""))[:200],
                    })

        recommended = str(raw.get("recommended_action", "skip"))[:20]
        valid_actions = {"retry", "switch_tool", "modify_params", "skip", "escalate"}
        if recommended not in valid_actions:
            recommended = "skip"

        return RecoveryReasoning(
            analysis=analysis,
            root_cause=root_cause,
            recovery_options=recovery_options,
            recommended_action=recommended,
        )
