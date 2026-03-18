"""Multi-Hypothesis Execution (Innovation #2).

Tracks competing hypotheses during task execution, updates confidence
with Bayesian-style evidence, and signals when hypotheses should be
abandoned or branched.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

logger = logging.getLogger(__name__)

# Thresholds
_ABANDON_THRESHOLD = 0.2
_PRUNE_THRESHOLD = 0.15
_BRANCH_DELTA = 0.10  # top-2 confidence gap below which branching is suggested


@dataclass
class Hypothesis:
    """A single hypothesis being tracked during execution."""

    id: str
    statement: str
    initial_confidence: float
    confidence: float  # current confidence (0.0 – 1.0)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    update_history: list[dict[str, Any]] = field(default_factory=list)


class HypothesisTracker:
    """Track and update competing hypotheses throughout execution."""

    def __init__(self) -> None:
        self._hypotheses: dict[str, Hypothesis] = {}

    @property
    def hypotheses(self) -> list[Hypothesis]:
        return list(self._hypotheses.values())

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate_hypotheses(
        self,
        task_goal: str,
        evidence_pool: list[str],
        num_hypotheses: int = 3,
    ) -> list[Hypothesis]:
        """Generate initial hypotheses from the task goal and any early evidence."""
        if not has_openai_credentials():
            # Fallback: single default hypothesis.
            h = Hypothesis(
                id=str(uuid.uuid4()),
                statement=f"Direct approach to: {task_goal[:200]}",
                initial_confidence=0.6,
                confidence=0.6,
            )
            self._hypotheses[h.id] = h
            return [h]

        evidence_text = "\n".join(evidence_pool[:8])[:2000] if evidence_pool else "(none yet)"

        prompt = (
            "Given a task goal and initial evidence, generate {n} competing hypotheses "
            "about how to best accomplish the task. Each hypothesis should represent "
            "a different approach or interpretation.\n\n"
            "Task goal: {goal}\n"
            "Evidence so far:\n{evidence}\n\n"
            "Return JSON:\n"
            '{{"hypotheses": [{{"statement": "...", "initial_confidence": 0.0-1.0, '
            '"rationale": "..."}}]}}'
        ).format(
            n=num_hypotheses,
            goal=task_goal[:600],
            evidence=evidence_text,
        )

        try:
            payload = call_json_response(
                system_prompt="You are a hypothesis generation engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.5,
                timeout_seconds=12,
                max_tokens=800,
            )
        except Exception:
            logger.exception("HypothesisTracker: generation failed — single fallback")
            h = Hypothesis(
                id=str(uuid.uuid4()),
                statement=f"Direct approach to: {task_goal[:200]}",
                initial_confidence=0.6,
                confidence=0.6,
            )
            self._hypotheses[h.id] = h
            return [h]

        if not isinstance(payload, dict):
            return []

        raw = payload.get("hypotheses")
        if not isinstance(raw, list):
            return []

        results: list[Hypothesis] = []
        for item in raw[:num_hypotheses]:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            if not statement:
                continue
            conf = float(item.get("initial_confidence") or 0.5)
            conf = max(0.0, min(1.0, conf))
            h = Hypothesis(
                id=str(uuid.uuid4()),
                statement=statement[:400],
                initial_confidence=conf,
                confidence=conf,
            )
            self._hypotheses[h.id] = h
            results.append(h)

        return results

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_hypothesis(
        self,
        hypothesis_id: str,
        new_evidence: str,
        outcome: str,
    ) -> Hypothesis | None:
        """Bayesian-style confidence update based on new evidence.

        *outcome* should be one of: "supports", "contradicts", "neutral".
        """
        h = self._hypotheses.get(hypothesis_id)
        if h is None:
            return None

        old_confidence = h.confidence
        evidence_snippet = new_evidence.strip()[:300]

        if outcome == "supports":
            # Increase confidence — diminishing returns as it approaches 1.0.
            boost = 0.10 * (1.0 - h.confidence)
            h.confidence = min(1.0, h.confidence + max(boost, 0.02))
            h.supporting_evidence.append(evidence_snippet)
        elif outcome == "contradicts":
            # Decrease confidence — accelerating as confidence drops.
            drop = 0.12 * h.confidence
            h.confidence = max(0.0, h.confidence - max(drop, 0.03))
            h.contradicting_evidence.append(evidence_snippet)
        # "neutral" — no change.

        h.update_history.append(
            {
                "evidence": evidence_snippet[:120],
                "outcome": outcome,
                "old_confidence": round(old_confidence, 3),
                "new_confidence": round(h.confidence, 3),
            }
        )

        return h

    def update_all_hypotheses(
        self,
        new_evidence: str,
    ) -> list[Hypothesis]:
        """Use LLM to determine how new evidence affects each hypothesis."""
        if not self._hypotheses or not new_evidence.strip():
            return self.hypotheses

        if not has_openai_credentials():
            return self.hypotheses

        hyp_summaries = [
            {"id": h.id, "statement": h.statement[:200], "confidence": h.confidence}
            for h in self._hypotheses.values()
        ]

        prompt = (
            "Given new evidence, determine how it affects each hypothesis.\n\n"
            f"New evidence: {new_evidence[:600]}\n\n"
            f"Hypotheses: {json.dumps(hyp_summaries)}\n\n"
            "For each hypothesis, classify the evidence impact as: "
            '"supports", "contradicts", or "neutral".\n\n'
            "Return JSON:\n"
            '{"impacts": [{"id": "...", "outcome": "supports|contradicts|neutral"}]}'
        )

        try:
            payload = call_json_response(
                system_prompt="You are a hypothesis evaluation engine. Output strict JSON only.",
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=10,
                max_tokens=400,
            )
        except Exception:
            logger.exception("HypothesisTracker: bulk update failed")
            return self.hypotheses

        if isinstance(payload, dict):
            impacts = payload.get("impacts")
            if isinstance(impacts, list):
                for imp in impacts:
                    if not isinstance(imp, dict):
                        continue
                    hid = str(imp.get("id") or "")
                    outcome = str(imp.get("outcome") or "neutral").strip().lower()
                    if outcome not in ("supports", "contradicts", "neutral"):
                        outcome = "neutral"
                    if hid in self._hypotheses:
                        self.update_hypothesis(hid, new_evidence, outcome)

        return self.hypotheses

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_leading_hypothesis(self) -> Hypothesis | None:
        """Return the hypothesis with the highest confidence."""
        if not self._hypotheses:
            return None
        return max(self._hypotheses.values(), key=lambda h: h.confidence)

    def should_abandon(self, hypothesis: Hypothesis) -> bool:
        """True if confidence has dropped below the abandon threshold."""
        return hypothesis.confidence < _ABANDON_THRESHOLD

    def should_branch(self, hypotheses: list[Hypothesis] | None = None) -> bool:
        """True if the top 2 hypotheses are very close in confidence."""
        pool = hypotheses if hypotheses is not None else self.hypotheses
        if len(pool) < 2:
            return False
        sorted_pool = sorted(pool, key=lambda h: h.confidence, reverse=True)
        delta = sorted_pool[0].confidence - sorted_pool[1].confidence
        return delta < _BRANCH_DELTA

    def prune_hypotheses(self, min_confidence: float = _PRUNE_THRESHOLD) -> list[Hypothesis]:
        """Remove hypotheses below min_confidence. Returns removed items."""
        to_remove = [
            h for h in self._hypotheses.values()
            if h.confidence < min_confidence
        ]
        for h in to_remove:
            del self._hypotheses[h.id]
        return to_remove
