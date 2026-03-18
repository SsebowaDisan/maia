"""Prospective reasoning — Brain estimates success BEFORE committing.

Innovation #1: Before executing a step the Brain asks "Given what we know,
will this step likely succeed?" and can suggest an alternative when the
probability is too low.

This avoids wasting tool calls on approaches that are unlikely to work
based on prior evidence and failure patterns.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepForecast:
    """Result of prospective success estimation for a planned step."""
    tool_id: str
    estimated_success_probability: float
    reasoning: str
    risk_factors: list[str] = field(default_factory=list)
    recommended_params_adjustments: dict[str, Any] = field(default_factory=dict)


_ESTIMATE_SYSTEM_PROMPT = """\
You are a predictive reasoning engine for an AI agent.
Your job is to estimate the probability that a planned tool step will succeed,
given prior execution history, evidence already collected, and known failure
patterns.

Rules:
- Return ONLY valid JSON — no prose, no markdown.
- probability is a float between 0.0 and 1.0.
- Be realistic: if the same tool already failed with similar params, lower the
  probability significantly.
- Consider evidence gaps: if needed inputs are missing, probability drops.
- risk_factors: short list of what could go wrong.
- recommended_params_adjustments: suggest concrete param changes that would
  improve success (empty dict if none).
"""

_ESTIMATE_USER_TEMPLATE = """\
STEP TO EVALUATE:
  tool_id: {tool_id}
  title: {step_title}
  params: {step_params}
  why: {why_this_step}

PRIOR TOOL HISTORY (most recent last):
{tool_history}

EVIDENCE COLLECTED SO FAR:
{evidence_pool}

LEARNED RULES / PATTERNS:
{learned_rules}

Estimate the probability this step will succeed and explain your reasoning.

Return JSON:
{{
  "probability": <float 0.0-1.0>,
  "reasoning": "<one paragraph explaining your estimate>",
  "risk_factors": ["<risk1>", "<risk2>"],
  "recommended_params_adjustments": {{}}
}}
"""

_ALTERNATIVE_SYSTEM_PROMPT = """\
You are a tool selection advisor for an AI agent.
A planned step has a low predicted success probability.  Suggest an alternative
tool + params combination that is more likely to succeed, given what has already
been tried and what evidence is available.

Rules:
- Return ONLY valid JSON — no prose.
- Use only tool IDs from the available list.
- Do not suggest a tool+params combo that already failed.
- If no good alternative exists, return: {"alternative": null}
"""

_ALTERNATIVE_USER_TEMPLATE = """\
ORIGINAL STEP (low probability: {probability:.2f}):
  tool_id: {tool_id}
  reasoning: {reasoning}
  risk_factors: {risk_factors}

AVAILABLE TOOLS:
  {available_tools}

PRIOR TOOL HISTORY:
{tool_history}

EVIDENCE SO FAR:
{evidence_pool}

Suggest an alternative step or return {{"alternative": null}}.

Return JSON:
{{
  "alternative": {{
    "tool_id": "<tool_id>",
    "title": "<short title>",
    "params": {{}},
    "why_this_step": "<why this is better>",
    "expected_evidence": ["<what it should find>"]
  }}
}}
"""


def _format_tool_history(tool_history: list[dict[str, Any]]) -> str:
    if not tool_history:
        return "  (no prior tool executions)"
    lines: list[str] = []
    for i, entry in enumerate(tool_history[-10:], 1):
        status = str(entry.get("status", "unknown"))
        tool_id = str(entry.get("tool_id", "unknown"))
        summary = str(entry.get("content_summary", ""))[:120]
        error = str(entry.get("error_message", ""))[:80]
        detail = summary if status != "failed" else f"ERROR: {error}"
        lines.append(f"  {i}. [{status}] {tool_id} — {detail}")
    return "\n".join(lines)


def _format_evidence(evidence_pool: list[str]) -> str:
    if not evidence_pool:
        return "  (no evidence collected yet)"
    return "\n".join(f"  - {e[:200]}" for e in evidence_pool[-8:])


def _format_learned_rules(learned_rules: list[dict[str, Any]]) -> str:
    if not learned_rules:
        return "  (no learned patterns)"
    lines: list[str] = []
    for rule in learned_rules[-6:]:
        lines.append(f"  - {str(rule.get('rule', rule))[:150]}")
    return "\n".join(lines)


class ProspectiveReasoner:
    """Estimates step success probability before committing to execution.

    Uses LLM-based prediction informed by tool execution history,
    evidence pool, and learned failure patterns.
    """

    def estimate_step_success(
        self,
        step: dict[str, Any],
        evidence_pool: list[str],
        tool_history: list[dict[str, Any]],
        learned_rules: list[dict[str, Any]] | None = None,
    ) -> StepForecast:
        """Estimate the probability that a step will succeed.

        Parameters
        ----------
        step:
            Dict with tool_id, title, params, why_this_step.
        evidence_pool:
            Accumulated evidence strings from prior steps.
        tool_history:
            List of dicts with tool_id, status, content_summary, error_message.
        learned_rules:
            Optional list of learned patterns / rules from prior failures.

        Returns
        -------
        StepForecast with probability, reasoning, risk factors, and
        recommended parameter adjustments.
        """
        import json

        tool_id = str(step.get("tool_id", ""))
        step_title = str(step.get("title", ""))
        step_params = step.get("params", {})
        why = str(step.get("why_this_step", ""))

        prompt = _ESTIMATE_USER_TEMPLATE.format(
            tool_id=tool_id,
            step_title=step_title,
            step_params=json.dumps(step_params, default=str)[:300],
            why_this_step=why[:200],
            tool_history=_format_tool_history(tool_history),
            evidence_pool=_format_evidence(evidence_pool),
            learned_rules=_format_learned_rules(learned_rules or []),
        )

        try:
            raw = call_json_response(
                system_prompt=_ESTIMATE_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.1,
                timeout_seconds=12,
            )
        except Exception as exc:
            logger.debug("prospective.estimate_failed error=%s", exc)
            return StepForecast(
                tool_id=tool_id,
                estimated_success_probability=0.6,
                reasoning=f"Estimation failed ({exc}); defaulting to moderate probability.",
                risk_factors=["estimation_error"],
            )

        if not isinstance(raw, dict):
            return StepForecast(
                tool_id=tool_id,
                estimated_success_probability=0.6,
                reasoning="LLM returned non-dict; defaulting to moderate probability.",
                risk_factors=["parse_error"],
            )

        probability = raw.get("probability", 0.6)
        try:
            probability = float(probability)
        except (TypeError, ValueError):
            probability = 0.6
        probability = max(0.0, min(1.0, probability))

        reasoning = str(raw.get("reasoning", ""))[:500]
        risk_factors_raw = raw.get("risk_factors", [])
        if isinstance(risk_factors_raw, list):
            risk_factors = [str(r)[:120] for r in risk_factors_raw[:6]]
        else:
            risk_factors = []

        adjustments_raw = raw.get("recommended_params_adjustments", {})
        if not isinstance(adjustments_raw, dict):
            adjustments_raw = {}

        return StepForecast(
            tool_id=tool_id,
            estimated_success_probability=probability,
            reasoning=reasoning,
            risk_factors=risk_factors,
            recommended_params_adjustments=dict(adjustments_raw),
        )

    def should_proceed(
        self,
        forecast: StepForecast,
        min_probability: float = 0.4,
    ) -> bool:
        """Decide whether to proceed with the step based on the forecast.

        Returns True if the estimated probability meets the minimum threshold.
        """
        return forecast.estimated_success_probability >= min_probability

    def suggest_alternative(
        self,
        forecast: StepForecast,
        available_tools: list[str],
        evidence_pool: list[str] | None = None,
        tool_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Suggest an alternative tool+params when probability is too low.

        Parameters
        ----------
        forecast:
            The low-probability forecast for the original step.
        available_tools:
            List of tool IDs the agent can use.
        evidence_pool:
            Accumulated evidence from prior steps.
        tool_history:
            Prior tool execution history.

        Returns
        -------
        A dict with tool_id, title, params, why_this_step, expected_evidence
        or None if no good alternative exists.
        """
        import json

        prompt = _ALTERNATIVE_USER_TEMPLATE.format(
            probability=forecast.estimated_success_probability,
            tool_id=forecast.tool_id,
            reasoning=forecast.reasoning[:300],
            risk_factors=json.dumps(forecast.risk_factors, default=str)[:200],
            available_tools=", ".join(available_tools[:30]),
            tool_history=_format_tool_history(tool_history or []),
            evidence_pool=_format_evidence(evidence_pool or []),
        )

        try:
            raw = call_json_response(
                system_prompt=_ALTERNATIVE_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
                timeout_seconds=12,
            )
        except Exception as exc:
            logger.debug("prospective.suggest_alternative_failed error=%s", exc)
            return None

        if not isinstance(raw, dict):
            return None

        alt = raw.get("alternative")
        if not isinstance(alt, dict):
            return None

        alt_tool_id = str(alt.get("tool_id", "")).strip()
        if not alt_tool_id or alt_tool_id not in available_tools:
            return None

        return {
            "tool_id": alt_tool_id,
            "title": str(alt.get("title", ""))[:120],
            "params": alt.get("params") if isinstance(alt.get("params"), dict) else {},
            "why_this_step": str(alt.get("why_this_step", ""))[:200],
            "expected_evidence": tuple(
                str(e) for e in (alt.get("expected_evidence") or [])[:4]
            ),
        }
