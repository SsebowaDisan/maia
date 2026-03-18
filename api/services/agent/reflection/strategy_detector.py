"""Strategy detector — detects stuck agents and suggests pivots.

Analyses step history and evidence pool for patterns indicating the
agent is stuck: repeated tool failures, evidence plateaus, circular
reasoning, or resource exhaustion.

Environment
-----------
MAIA_STRATEGY_DETECTOR_ENABLED  (default "true") — set "false" to disable
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

logger = logging.getLogger(__name__)

_ENABLED = env_bool("MAIA_STRATEGY_DETECTOR_ENABLED", default=True)

_CONSECUTIVE_FAILURE_THRESHOLD = 3
_EVIDENCE_PLATEAU_WINDOW = 3

_STUCK_TYPES = {
    "repeated_failures",
    "evidence_plateau",
    "circular_reasoning",
    "resource_exhaustion",
}

_PIVOT_SYSTEM_PROMPT = (
    "You are a strategy advisor for an AI agent that appears stuck. "
    "Given the current approach, failure patterns, and available tools, "
    "suggest a pivot to a different strategy. "
    "Return ONLY valid JSON — no prose, no markdown."
)

_PIVOT_USER_TEMPLATE = """\
CURRENT STRATEGY:
  {current_strategy}

STUCK REPORT:
  Type: {stuck_type}
  Consecutive failures: {consecutive_failures}
  Evidence plateau: {evidence_plateau}
  Suggested pivot: {suggested_pivot}

RECENT STEP HISTORY:
{step_history_block}

AVAILABLE TOOLS:
{tools_block}

Suggest a new approach that avoids the patterns causing stuckness.

Return JSON:
{{
  "new_approach": "<brief description of the new strategy>",
  "rationale": "<why this is better than the current approach>",
  "new_steps": [
    {{
      "tool_id": "<tool from available list>",
      "title": "<what this step does>",
      "params": {{}},
      "why_this_step": "<how this helps>"
    }}
  ]
}}
"""


@dataclass(frozen=True)
class StucknessReport:
    """Assessment of whether the agent is stuck."""
    is_stuck: bool
    stuck_type: str  # one of _STUCK_TYPES or ""
    consecutive_failures: int
    evidence_plateau: bool
    suggested_pivot: str


@dataclass(frozen=True)
class StrategyPivot:
    """A recommended strategy change."""
    new_approach: str
    rationale: str
    new_steps: list[dict[str, Any]]


class StrategyDetector:
    """Detects when an agent is stuck and suggests strategy pivots."""

    def detect_stuckness(
        self,
        step_history: list[dict[str, Any]],
        evidence_pool: list[str],
    ) -> StucknessReport:
        """Analyze step history and evidence for stuckness patterns.

        Checks for:
        - Same tool failing 3+ consecutive times
        - No new evidence for 3+ steps
        - Same search queries repeated
        - All steps failing
        """
        if not _ENABLED or not step_history:
            return StucknessReport(
                is_stuck=False,
                stuck_type="",
                consecutive_failures=0,
                evidence_plateau=False,
                suggested_pivot="",
            )

        # Check consecutive failures
        consecutive_failures = _count_consecutive_failures(step_history)
        is_repeated_failures = consecutive_failures >= _CONSECUTIVE_FAILURE_THRESHOLD

        # Check evidence plateau
        evidence_plateau = _detect_evidence_plateau(step_history, evidence_pool)

        # Check circular reasoning (same tool+query repeated)
        is_circular = _detect_circular_patterns(step_history)

        # Check resource exhaustion (all recent steps failed)
        recent = step_history[-5:]
        all_failed = len(recent) >= 3 and all(
            str(s.get("status", "")).lower() in {"failed", "blocked", "empty"}
            for s in recent
        )

        # Determine stuck type and overall verdict
        stuck_type = ""
        suggested_pivot = ""

        if is_repeated_failures:
            stuck_type = "repeated_failures"
            failing_tool = _most_common_failing_tool(step_history)
            suggested_pivot = (
                f"Tool '{failing_tool}' has failed {consecutive_failures} consecutive times. "
                f"Try an alternative tool or different parameters."
            )
        elif evidence_plateau:
            stuck_type = "evidence_plateau"
            suggested_pivot = (
                "No new evidence has been gathered in recent steps. "
                "Try different search terms, a different data source, or broaden the query."
            )
        elif is_circular:
            stuck_type = "circular_reasoning"
            suggested_pivot = (
                "The same tool and query patterns are being repeated. "
                "Break the cycle by trying a fundamentally different approach."
            )
        elif all_failed:
            stuck_type = "resource_exhaustion"
            suggested_pivot = (
                "All recent steps have failed. Consider escalating to human review "
                "or trying a completely different tool category."
            )

        is_stuck = bool(stuck_type)

        return StucknessReport(
            is_stuck=is_stuck,
            stuck_type=stuck_type,
            consecutive_failures=consecutive_failures,
            evidence_plateau=evidence_plateau,
            suggested_pivot=suggested_pivot,
        )

    def suggest_strategy_pivot(
        self,
        current_strategy: str,
        stuck_report: StucknessReport,
        available_tools: list[str],
    ) -> StrategyPivot:
        """Generate a concrete strategy pivot using LLM reasoning."""
        if not _ENABLED or not stuck_report.is_stuck:
            return StrategyPivot(
                new_approach="",
                rationale="Agent is not stuck; no pivot needed.",
                new_steps=[],
            )

        tools_block = "\n".join(f"  - {t}" for t in available_tools[:20]) or "  (none)"

        prompt = _PIVOT_USER_TEMPLATE.format(
            current_strategy=current_strategy[:300] or "(no explicit strategy)",
            stuck_type=stuck_report.stuck_type,
            consecutive_failures=stuck_report.consecutive_failures,
            evidence_plateau=stuck_report.evidence_plateau,
            suggested_pivot=stuck_report.suggested_pivot[:200],
            step_history_block="  (see stuck report)",
            tools_block=tools_block,
        )

        try:
            raw = call_json_response(
                system_prompt=_PIVOT_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=12,
                max_tokens=400,
            )
            if not isinstance(raw, dict):
                return StrategyPivot(
                    new_approach=stuck_report.suggested_pivot,
                    rationale="LLM pivot failed; using deterministic suggestion.",
                    new_steps=[],
                )

            new_steps_raw = raw.get("new_steps", [])
            new_steps: list[dict[str, Any]] = []
            if isinstance(new_steps_raw, list):
                tool_set = {t.strip() for t in available_tools if t.strip()}
                for item in new_steps_raw[:3]:
                    if not isinstance(item, dict):
                        continue
                    tool_id = str(item.get("tool_id", "")).strip()
                    if not tool_id:
                        continue
                    if tool_set and tool_id not in tool_set:
                        continue
                    new_steps.append({
                        "tool_id": tool_id,
                        "title": str(item.get("title", tool_id))[:120],
                        "params": dict(item.get("params") or {}) if isinstance(item.get("params"), dict) else {},
                        "why_this_step": str(item.get("why_this_step", ""))[:200],
                    })

            return StrategyPivot(
                new_approach=str(raw.get("new_approach", ""))[:300],
                rationale=str(raw.get("rationale", ""))[:300],
                new_steps=new_steps,
            )
        except Exception as exc:
            logger.debug("strategy_detector.suggest_pivot failed: %s", exc)
            return StrategyPivot(
                new_approach=stuck_report.suggested_pivot,
                rationale=f"LLM pivot failed: {str(exc)[:100]}",
                new_steps=[],
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_consecutive_failures(step_history: list[dict[str, Any]]) -> int:
    """Count trailing consecutive failures in step history."""
    count = 0
    for step in reversed(step_history):
        status = str(step.get("status", "")).lower()
        if status in {"failed", "blocked", "empty"}:
            count += 1
        else:
            break
    return count


def _detect_evidence_plateau(
    step_history: list[dict[str, Any]],
    evidence_pool: list[str],
) -> bool:
    """True if the last N steps produced no new evidence."""
    if len(step_history) < _EVIDENCE_PLATEAU_WINDOW:
        return False

    recent = step_history[-_EVIDENCE_PLATEAU_WINDOW:]
    for step in recent:
        summary = str(step.get("summary", "")).strip()
        evidence_count = int(step.get("evidence_count", 0) or 0)
        if summary and evidence_count > 0:
            return False
    return True


def _detect_circular_patterns(step_history: list[dict[str, Any]]) -> bool:
    """True if the same tool+query combination appears 3+ times."""
    if len(step_history) < 3:
        return False

    signatures: list[str] = []
    for step in step_history:
        tool_id = str(step.get("tool_id", "")).strip()
        params = step.get("params", {})
        query = str(params.get("query", "") if isinstance(params, dict) else "").strip().lower()
        sig = f"{tool_id}:{query}"
        signatures.append(sig)

    counts = Counter(signatures)
    return any(count >= 3 for count in counts.values())


def _most_common_failing_tool(step_history: list[dict[str, Any]]) -> str:
    """Return the tool_id that failed most recently and frequently."""
    failing_tools: list[str] = []
    for step in reversed(step_history):
        status = str(step.get("status", "")).lower()
        if status in {"failed", "blocked", "empty"}:
            failing_tools.append(str(step.get("tool_id", "unknown")))
        else:
            break
    if not failing_tools:
        return "unknown"
    counts = Counter(failing_tools)
    return counts.most_common(1)[0][0]
