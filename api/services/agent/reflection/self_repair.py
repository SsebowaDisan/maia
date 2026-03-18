"""Self-repair loop (Innovation #10).

Diagnoses verification failures and generates repair plans that the
orchestrator can inject as additional steps.  Tracks repair attempts
to avoid infinite loops and enable learning.

Environment
-----------
MAIA_SELF_REPAIR_ENABLED       (default "true") — set "false" to disable
MAIA_SELF_REPAIR_MAX_BUDGET    (default "2")    — max repair cycles per run
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

logger = logging.getLogger(__name__)

_ENABLED = env_bool("MAIA_SELF_REPAIR_ENABLED", default=True)
_DEFAULT_BUDGET = int(os.environ.get("MAIA_SELF_REPAIR_MAX_BUDGET", "2"))

_FAILURE_TYPES = {
    "missing_evidence",
    "low_confidence",
    "contradicting_claims",
    "incomplete_actions",
    "tool_failures",
}

_REPAIR_STRATEGIES = {
    "retry_with_different_tool",
    "add_verification_steps",
    "refine_search_query",
    "decompose_into_substeps",
    "escalate_to_human",
}

_DIAGNOSE_SYSTEM_PROMPT = (
    "You are a failure diagnostician for an AI agent. "
    "Given a verification result showing problems and the step history, "
    "determine the root cause and best repair strategy. "
    "Return ONLY valid JSON — no prose, no markdown."
)

_DIAGNOSE_USER_TEMPLATE = """\
VERIFICATION RESULT:
  Score: {score}%
  Grade: {grade}
  Warning checks: {warning_checks}
  Unsupported claims: {unsupported_claims}
  Contradictions: {contradictions}

STEP HISTORY (last {step_count} steps):
{step_history_block}

EVIDENCE POOL (last {evidence_count} items):
{evidence_block}

Diagnose the failure and suggest a repair strategy.

Return JSON:
{{
  "failure_type": "<one of: missing_evidence, low_confidence, contradicting_claims, incomplete_actions, tool_failures>",
  "root_cause": "<one sentence describing the root cause>",
  "repair_strategy": "<one of: retry_with_different_tool, add_verification_steps, refine_search_query, decompose_into_substeps, escalate_to_human>",
  "steps_to_retry": [
    {{"tool_id": "...", "title": "...", "params": {{}}, "why_this_step": "..."}}
  ],
  "new_steps": [
    {{"tool_id": "...", "title": "...", "params": {{}}, "why_this_step": "..."}}
  ]
}}
"""

_REPAIR_PLAN_SYSTEM_PROMPT = (
    "You are a repair planner for an AI agent. "
    "Given a failure diagnosis and available tools, "
    "generate concrete steps to fix the issue. "
    "Return ONLY valid JSON — no prose, no markdown."
)

_REPAIR_PLAN_USER_TEMPLATE = """\
DIAGNOSIS:
  Failure type: {failure_type}
  Root cause: {root_cause}
  Repair strategy: {repair_strategy}

AVAILABLE TOOLS:
{tools_block}

Generate a repair plan with concrete steps.

Return JSON:
{{
  "steps": [
    {{
      "tool_id": "<tool from available list>",
      "title": "<what this step does>",
      "params": {{}},
      "why_this_step": "<how this fixes the issue>"
    }}
  ]
}}

Rules:
- Maximum 3 steps
- Only use tools from the available list
- Each step must directly address the diagnosed issue
"""


@dataclass(frozen=True)
class RepairDiagnosis:
    """Result of diagnosing a verification failure."""
    failure_type: str
    root_cause: str
    repair_strategy: str
    steps_to_retry: list[dict[str, Any]]
    new_steps: list[dict[str, Any]]


@dataclass
class RepairAttempt:
    """Record of a single repair attempt for tracking."""
    run_id: str
    cycle: int
    diagnosis: RepairDiagnosis
    outcome: str  # "success", "partial", "failed"
    timestamp_ms: int = field(default_factory=lambda: int(time.monotonic() * 1000))


class SelfRepairEngine:
    """Diagnoses verification failures and generates repair plans."""

    def __init__(self) -> None:
        self._repair_history: list[RepairAttempt] = []

    def should_repair(
        self,
        verification_result: dict[str, Any],
        repair_budget: int = _DEFAULT_BUDGET,
    ) -> bool:
        """Decide whether a repair attempt is worth making.

        Returns True if:
        - Self-repair is enabled
        - There are actionable warnings/failures
        - Budget has not been exhausted
        """
        if not _ENABLED:
            return False

        cycles_used = len(self._repair_history)
        if cycles_used >= repair_budget:
            logger.debug(
                "self_repair.budget_exhausted cycles=%d budget=%d",
                cycles_used, repair_budget,
            )
            return False

        score = float(verification_result.get("score", 100.0))
        grade = str(verification_result.get("grade", "strong")).lower()
        checks = verification_result.get("checks", [])
        warning_count = sum(
            1 for c in checks
            if isinstance(c, dict) and str(c.get("status", "")).lower() in {"warn", "fail", "warning"}
        )
        unsupported = verification_result.get("unsupported_claims", [])
        contradictions = verification_result.get("contradictions", [])

        # Don't repair if everything looks good
        if grade == "strong" and warning_count == 0:
            return False

        # Repair if there are meaningful issues
        if warning_count >= 2 or len(unsupported) >= 2 or len(contradictions) >= 1:
            return True

        # Repair if score is below fair threshold
        if score < 60.0:
            return True

        return False

    def diagnose_failure(
        self,
        verification_result: dict[str, Any],
        step_history: list[dict[str, Any]],
        evidence_pool: list[str],
    ) -> RepairDiagnosis:
        """Diagnose why verification failed and suggest repair approach."""
        if not _ENABLED:
            return RepairDiagnosis(
                failure_type="tool_failures",
                root_cause="Self-repair disabled.",
                repair_strategy="escalate_to_human",
                steps_to_retry=[],
                new_steps=[],
            )

        checks = verification_result.get("checks", [])
        warning_checks = [
            f"{c.get('name', '?')}: {c.get('detail', '')[:80]}"
            for c in checks
            if isinstance(c, dict) and str(c.get("status", "")).lower() in {"warn", "fail", "warning"}
        ]
        unsupported = verification_result.get("unsupported_claims", [])
        contradictions = verification_result.get("contradictions", [])

        step_block_items = []
        for s in step_history[-8:]:
            tool_id = str(s.get("tool_id", "?"))
            status = str(s.get("status", "?"))
            summary = str(s.get("summary", ""))[:120]
            step_block_items.append(f"  [{status}] {tool_id}: {summary}")
        step_history_block = "\n".join(step_block_items) or "  (no steps recorded)"

        evidence_block_items = [f"  - {e[:200]}" for e in evidence_pool[-8:]]
        evidence_block = "\n".join(evidence_block_items) or "  (no evidence)"

        prompt = _DIAGNOSE_USER_TEMPLATE.format(
            score=verification_result.get("score", "?"),
            grade=verification_result.get("grade", "?"),
            warning_checks="; ".join(warning_checks[:6]) or "none",
            unsupported_claims="; ".join(str(c)[:80] for c in unsupported[:4]) or "none",
            contradictions=str(len(contradictions)),
            step_count=len(step_history[-8:]),
            step_history_block=step_history_block,
            evidence_count=len(evidence_pool[-8:]),
            evidence_block=evidence_block,
        )

        try:
            raw = call_json_response(
                system_prompt=_DIAGNOSE_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=14,
                max_tokens=500,
            )
            if not isinstance(raw, dict):
                return self._fallback_diagnosis(verification_result)

            failure_type = str(raw.get("failure_type", "missing_evidence")).strip()
            if failure_type not in _FAILURE_TYPES:
                failure_type = "missing_evidence"

            repair_strategy = str(raw.get("repair_strategy", "add_verification_steps")).strip()
            if repair_strategy not in _REPAIR_STRATEGIES:
                repair_strategy = "add_verification_steps"

            return RepairDiagnosis(
                failure_type=failure_type,
                root_cause=str(raw.get("root_cause", ""))[:300],
                repair_strategy=repair_strategy,
                steps_to_retry=_clean_step_list(raw.get("steps_to_retry"), 3),
                new_steps=_clean_step_list(raw.get("new_steps"), 3),
            )
        except Exception as exc:
            logger.debug("self_repair.diagnose_failure failed: %s", exc)
            return self._fallback_diagnosis(verification_result)

    def generate_repair_plan(
        self,
        diagnosis: RepairDiagnosis,
        available_tools: list[str],
    ) -> list[dict[str, Any]]:
        """Generate concrete repair steps based on the diagnosis."""
        if not _ENABLED:
            return []

        # If diagnosis already includes steps, use those
        if diagnosis.new_steps:
            return _filter_steps_by_tools(diagnosis.new_steps, available_tools)[:3]

        if diagnosis.repair_strategy == "escalate_to_human":
            return []

        tools_block = "\n".join(f"  - {t}" for t in available_tools[:20]) or "  (none)"

        prompt = _REPAIR_PLAN_USER_TEMPLATE.format(
            failure_type=diagnosis.failure_type,
            root_cause=diagnosis.root_cause[:200],
            repair_strategy=diagnosis.repair_strategy,
            tools_block=tools_block,
        )

        try:
            raw = call_json_response(
                system_prompt=_REPAIR_PLAN_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=12,
                max_tokens=400,
            )
            if not isinstance(raw, dict):
                return []
            steps = _clean_step_list(raw.get("steps"), 3)
            return _filter_steps_by_tools(steps, available_tools)
        except Exception as exc:
            logger.debug("self_repair.generate_repair_plan failed: %s", exc)
            return []

    def record_repair_attempt(
        self,
        run_id: str,
        diagnosis: RepairDiagnosis,
        outcome: str,
    ) -> None:
        """Track a repair attempt for learning and budget enforcement."""
        attempt = RepairAttempt(
            run_id=run_id,
            cycle=len(self._repair_history) + 1,
            diagnosis=diagnosis,
            outcome=outcome,
        )
        self._repair_history.append(attempt)
        logger.info(
            "self_repair.attempt_recorded run=%s cycle=%d type=%s strategy=%s outcome=%s",
            run_id, attempt.cycle, diagnosis.failure_type,
            diagnosis.repair_strategy, outcome,
        )

    @property
    def repair_cycle_count(self) -> int:
        return len(self._repair_history)

    def _fallback_diagnosis(
        self, verification_result: dict[str, Any],
    ) -> RepairDiagnosis:
        """Deterministic fallback when LLM diagnosis fails."""
        unsupported = verification_result.get("unsupported_claims", [])
        contradictions = verification_result.get("contradictions", [])

        if contradictions:
            return RepairDiagnosis(
                failure_type="contradicting_claims",
                root_cause="Contradictory evidence detected across sources.",
                repair_strategy="add_verification_steps",
                steps_to_retry=[],
                new_steps=[],
            )
        if unsupported:
            return RepairDiagnosis(
                failure_type="missing_evidence",
                root_cause="Key claims lack evidence support.",
                repair_strategy="refine_search_query",
                steps_to_retry=[],
                new_steps=[],
            )
        return RepairDiagnosis(
            failure_type="tool_failures",
            root_cause="Multiple tool steps produced warnings.",
            repair_strategy="retry_with_different_tool",
            steps_to_retry=[],
            new_steps=[],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_step_list(raw: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("tool_id", "")).strip()
        if not tool_id:
            continue
        result.append({
            "tool_id": tool_id,
            "title": str(item.get("title", tool_id))[:120],
            "params": dict(item.get("params") or {}) if isinstance(item.get("params"), dict) else {},
            "why_this_step": str(item.get("why_this_step", ""))[:200],
        })
    return result


def _filter_steps_by_tools(
    steps: list[dict[str, Any]],
    available_tools: list[str],
) -> list[dict[str, Any]]:
    """Keep only steps whose tool_id is in the available tools list."""
    if not available_tools:
        return steps  # No filtering if no tool list provided
    tool_set = {t.strip() for t in available_tools if t.strip()}
    return [s for s in steps if s.get("tool_id", "") in tool_set]
