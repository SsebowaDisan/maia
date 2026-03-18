"""Tree-of-Thought Planning (Innovation #6).

Generates multiple plan candidates for a task, scores them against the
task contract, and selects the best one while keeping alternatives for
fallback.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

logger = logging.getLogger(__name__)


@dataclass
class PlanCandidate:
    """A single plan option produced by the Tree-of-Thought generator."""

    plan_id: str
    steps: list[dict[str, Any]]
    rationale: str
    estimated_coverage: float  # 0.0 – 1.0
    estimated_cost: float  # relative cost estimate
    risk_assessment: str
    score: float = 0.0


class TreeOfThoughtPlanner:
    """Generate, score, and select among multiple plan strategies."""

    def __init__(self) -> None:
        self._alternatives: list[PlanCandidate] = []

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_plan_candidates(
        self,
        task_goal: str,
        available_tools: list[str],
        context: str,
        num_candidates: int = 3,
    ) -> list[PlanCandidate]:
        """Generate *num_candidates* different plan approaches via LLM.

        Each candidate takes a different strategy (e.g. broad search vs.
        targeted, single-source vs. multi-source).
        """
        if not has_openai_credentials():
            logger.debug("ToT: no LLM credentials — returning empty candidates")
            return []

        prompt = (
            "You are a planning strategist. Given a task goal and available tools, "
            "generate EXACTLY {n} alternative execution plans. Each plan should use "
            "a DIFFERENT strategy.\n\n"
            "Task goal: {goal}\n"
            "Available tools: {tools}\n"
            "Context: {ctx}\n\n"
            "Return ONLY valid JSON:\n"
            '{{\n  "candidates": [\n'
            "    {{\n"
            '      "strategy_name": "string",\n'
            '      "rationale": "why this approach",\n'
            '      "steps": [{{"tool_id": "...", "title": "...", "params": {{}}, '
            '"why_this_step": "...", "expected_evidence": ["..."]}}],\n'
            '      "estimated_coverage": 0.0-1.0,\n'
            '      "estimated_cost": 1-10,\n'
            '      "risk_assessment": "string"\n'
            "    }}\n"
            "  ]\n"
            "}}"
        ).format(
            n=num_candidates,
            goal=task_goal[:600],
            tools=json.dumps(available_tools[:60]),
            ctx=context[:400],
        )

        try:
            payload = call_json_response(
                system_prompt=(
                    "You are a multi-strategy planning engine. "
                    "Produce diverse plan candidates. Output strict JSON only."
                ),
                user_prompt=prompt,
                temperature=0.7,
                timeout_seconds=20,
                max_tokens=2400,
            )
        except Exception:
            logger.exception("ToT: LLM call failed during candidate generation")
            return []

        if not isinstance(payload, dict):
            return []

        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list):
            return []

        candidates: list[PlanCandidate] = []
        for item in raw_candidates[:num_candidates]:
            if not isinstance(item, dict):
                continue
            steps = item.get("steps")
            if not isinstance(steps, list) or not steps:
                continue
            candidates.append(
                PlanCandidate(
                    plan_id=str(uuid.uuid4()),
                    steps=steps,
                    rationale=str(item.get("rationale") or "")[:300],
                    estimated_coverage=float(item.get("estimated_coverage") or 0.5),
                    estimated_cost=float(item.get("estimated_cost") or 5.0),
                    risk_assessment=str(item.get("risk_assessment") or "unknown")[:200],
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_candidates(
        self,
        candidates: list[PlanCandidate],
        task_contract: dict[str, Any],
    ) -> list[PlanCandidate]:
        """LLM-score each plan on contract satisfaction, efficiency, and
        evidence diversity.  Returns the list sorted by score descending."""
        if not candidates:
            return []
        if not has_openai_credentials():
            # Heuristic fallback: use estimated_coverage as score.
            for c in candidates:
                c.score = c.estimated_coverage
            return sorted(candidates, key=lambda c: c.score, reverse=True)

        summaries = []
        for c in candidates:
            summaries.append(
                {
                    "plan_id": c.plan_id,
                    "rationale": c.rationale[:200],
                    "step_count": len(c.steps),
                    "tool_ids": [s.get("tool_id") for s in c.steps if isinstance(s, dict)][:10],
                    "estimated_coverage": c.estimated_coverage,
                    "estimated_cost": c.estimated_cost,
                    "risk_assessment": c.risk_assessment[:120],
                }
            )

        prompt = (
            "Score each plan candidate on a 0-1 scale considering:\n"
            "1. Likelihood of satisfying the task contract\n"
            "2. Efficiency (fewer steps with same coverage = better)\n"
            "3. Evidence diversity (using varied sources = better)\n\n"
            f"Task contract: {json.dumps(task_contract)[:600]}\n\n"
            f"Candidates: {json.dumps(summaries)}\n\n"
            'Return JSON: {{"scores": [{{"plan_id": "...", "score": 0.0-1.0, "reasoning": "..."}}]}}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a plan evaluation engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=15,
                max_tokens=1000,
            )
        except Exception:
            logger.exception("ToT: LLM scoring failed — falling back to heuristic")
            for c in candidates:
                c.score = c.estimated_coverage
            return sorted(candidates, key=lambda c: c.score, reverse=True)

        if isinstance(payload, dict):
            scores_list = payload.get("scores")
            if isinstance(scores_list, list):
                score_map = {
                    str(s.get("plan_id") or ""): float(s.get("score") or 0.0)
                    for s in scores_list
                    if isinstance(s, dict)
                }
                for c in candidates:
                    c.score = score_map.get(c.plan_id, c.estimated_coverage)

        return sorted(candidates, key=lambda c: c.score, reverse=True)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_best(self, candidates: list[PlanCandidate]) -> PlanCandidate | None:
        """Pick the highest-scoring candidate; store others for fallback."""
        if not candidates:
            return None
        sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
        best = sorted_candidates[0]
        self._alternatives = sorted_candidates[1:]
        return best

    @property
    def alternatives(self) -> list[PlanCandidate]:
        """Previously rejected candidates available for fallback."""
        return list(self._alternatives)
