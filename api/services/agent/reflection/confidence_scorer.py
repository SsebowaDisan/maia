"""Confidence-scored outputs (Innovation #8).

Provides calibrated confidence scores for every claim and the overall
response.  Uses structured LLM calls with temperature=0.0 for
consistency.

Environment
-----------
MAIA_CONFIDENCE_SCORER_ENABLED  (default "true") — set "false" to skip
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

logger = logging.getLogger(__name__)

_ENABLED = env_bool("MAIA_CONFIDENCE_SCORER_ENABLED", default=True)

_CLAIM_SYSTEM_PROMPT = (
    "You are a calibrated evidence assessor. "
    "Given a specific factual claim and a set of evidence texts, "
    "evaluate how well the evidence supports the claim. "
    "Be strict: speculation or tangential mentions do not count as support. "
    "Return ONLY valid JSON — no prose, no markdown."
)

_CLAIM_USER_TEMPLATE = """\
CLAIM:
  {claim_text}

EVIDENCE TEXTS:
{evidence_block}

Evaluate the evidence support for this claim.

Return JSON:
{{
  "confidence": <float 0.0-1.0>,
  "supporting_evidence_indices": [<int indices of evidence texts that support the claim>],
  "reasoning": "<one or two sentences explaining the confidence level>"
}}

Calibration guide:
- 0.0: No evidence at all
- 0.1-0.3: Tangential or very weak support
- 0.4-0.6: Partial support, key details missing or ambiguous
- 0.7-0.8: Good support from at least one source
- 0.9-1.0: Strong support from multiple independent sources
"""

_RESPONSE_SYSTEM_PROMPT = (
    "You are a calibrated response quality assessor. "
    "Given a response text, a list of claims it makes, and an evidence pool, "
    "evaluate the overall confidence level for the response. "
    "Return ONLY valid JSON — no prose, no markdown."
)

_RESPONSE_USER_TEMPLATE = """\
RESPONSE TEXT (excerpt):
  {response_excerpt}

CLAIMS MADE:
{claims_block}

EVIDENCE POOL:
{evidence_block}

Evaluate the overall quality and evidence support for this response.

Return JSON:
{{
  "overall_confidence": <float 0.0-1.0>,
  "weakest_claims": [<list of claim strings that have the least support>],
  "strongest_claims": [<list of claim strings that have the strongest support>],
  "reasoning": "<brief explanation of the overall confidence>"
}}
"""


@dataclass(frozen=True)
class ClaimScore:
    """Confidence score for a single claim."""
    claim: str
    confidence: float
    supporting_evidence: list[str]
    reasoning: str


@dataclass(frozen=True)
class ResponseScore:
    """Confidence score for an entire response."""
    overall_confidence: float
    claim_scores: list[ClaimScore]
    weakest_claims: list[str]
    strongest_claims: list[str]
    reasoning: str


class ConfidenceScorer:
    """Scores claims and responses with calibrated LLM-based confidence."""

    def score_claim(
        self,
        claim_text: str,
        evidence_texts: list[str],
    ) -> ClaimScore:
        """Score how well evidence supports a specific claim.

        Returns a ClaimScore with confidence 0.0-1.0.
        """
        if not _ENABLED or not claim_text.strip():
            return ClaimScore(
                claim=claim_text,
                confidence=0.0,
                supporting_evidence=[],
                reasoning="Confidence scoring disabled or empty claim.",
            )

        trimmed_evidence = [
            e.strip()[:400] for e in evidence_texts if e.strip()
        ][:12]

        if not trimmed_evidence:
            return ClaimScore(
                claim=claim_text,
                confidence=0.0,
                supporting_evidence=[],
                reasoning="No evidence texts provided.",
            )

        evidence_block = "\n".join(
            f"  [{i}] {text}" for i, text in enumerate(trimmed_evidence)
        )

        prompt = _CLAIM_USER_TEMPLATE.format(
            claim_text=claim_text.strip()[:300],
            evidence_block=evidence_block,
        )

        try:
            raw = call_json_response(
                system_prompt=_CLAIM_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=12,
                max_tokens=300,
            )
            if not isinstance(raw, dict):
                return ClaimScore(
                    claim=claim_text,
                    confidence=0.0,
                    supporting_evidence=[],
                    reasoning="LLM returned non-dict response.",
                )

            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
            indices = raw.get("supporting_evidence_indices", [])
            supporting = []
            if isinstance(indices, list):
                for idx in indices:
                    try:
                        i = int(idx)
                        if 0 <= i < len(trimmed_evidence):
                            supporting.append(trimmed_evidence[i])
                    except (ValueError, TypeError):
                        continue
            reasoning = str(raw.get("reasoning", ""))[:300]

            return ClaimScore(
                claim=claim_text,
                confidence=round(confidence, 3),
                supporting_evidence=supporting[:6],
                reasoning=reasoning,
            )
        except Exception as exc:
            logger.debug("confidence_scorer.score_claim failed: %s", exc)
            return ClaimScore(
                claim=claim_text,
                confidence=0.0,
                supporting_evidence=[],
                reasoning=f"Scoring failed: {str(exc)[:100]}",
            )

    def score_response(
        self,
        response_text: str,
        claims: list[str],
        evidence_pool: list[str],
    ) -> ResponseScore:
        """Score overall confidence for a response given its claims and evidence.

        Scores each claim individually, then asks the LLM for an overall assessment.
        """
        if not _ENABLED or not response_text.strip():
            return ResponseScore(
                overall_confidence=0.0,
                claim_scores=[],
                weakest_claims=[],
                strongest_claims=[],
                reasoning="Confidence scoring disabled or empty response.",
            )

        # Score individual claims
        claim_scores: list[ClaimScore] = []
        for claim in claims[:10]:
            score = self.score_claim(claim, evidence_pool)
            claim_scores.append(score)

        # Overall response-level assessment
        trimmed_evidence = [
            e.strip()[:300] for e in evidence_pool if e.strip()
        ][:10]
        claims_block = "\n".join(
            f"  - {c.strip()[:200]}" for c in claims[:10] if c.strip()
        )
        evidence_block = "\n".join(
            f"  [{i}] {text}" for i, text in enumerate(trimmed_evidence)
        )

        try:
            prompt = _RESPONSE_USER_TEMPLATE.format(
                response_excerpt=response_text.strip()[:1500],
                claims_block=claims_block or "  (no explicit claims extracted)",
                evidence_block=evidence_block or "  (no evidence available)",
            )
            raw = call_json_response(
                system_prompt=_RESPONSE_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.0,
                timeout_seconds=14,
                max_tokens=400,
            )
            if not isinstance(raw, dict):
                overall = _average_claim_confidence(claim_scores)
                return ResponseScore(
                    overall_confidence=overall,
                    claim_scores=claim_scores,
                    weakest_claims=_weakest(claim_scores, 3),
                    strongest_claims=_strongest(claim_scores, 3),
                    reasoning="LLM returned non-dict; fell back to average.",
                )

            overall = max(0.0, min(1.0, float(raw.get("overall_confidence", 0.0))))
            weakest = _clean_str_list(raw.get("weakest_claims"), 5)
            strongest = _clean_str_list(raw.get("strongest_claims"), 5)
            reasoning = str(raw.get("reasoning", ""))[:400]

            return ResponseScore(
                overall_confidence=round(overall, 3),
                claim_scores=claim_scores,
                weakest_claims=weakest,
                strongest_claims=strongest,
                reasoning=reasoning,
            )
        except Exception as exc:
            logger.debug("confidence_scorer.score_response failed: %s", exc)
            overall = _average_claim_confidence(claim_scores)
            return ResponseScore(
                overall_confidence=overall,
                claim_scores=claim_scores,
                weakest_claims=_weakest(claim_scores, 3),
                strongest_claims=_strongest(claim_scores, 3),
                reasoning=f"Overall scoring failed, fell back to average: {str(exc)[:100]}",
            )

    def generate_confidence_summary(self, response_score: ResponseScore) -> str:
        """Generate a human-readable confidence breakdown."""
        lines: list[str] = []
        lines.append(f"Overall Confidence: {response_score.overall_confidence:.0%}")
        lines.append("")

        if response_score.claim_scores:
            lines.append("Claim-level Scores:")
            for cs in response_score.claim_scores:
                indicator = (
                    "strong" if cs.confidence >= 0.8
                    else "moderate" if cs.confidence >= 0.5
                    else "weak"
                )
                lines.append(f"  [{indicator} {cs.confidence:.0%}] {cs.claim[:120]}")
            lines.append("")

        if response_score.weakest_claims:
            lines.append("Weakest Claims (consider additional verification):")
            for claim in response_score.weakest_claims[:3]:
                lines.append(f"  - {claim[:120]}")
            lines.append("")

        if response_score.strongest_claims:
            lines.append("Strongest Claims (well-supported):")
            for claim in response_score.strongest_claims[:3]:
                lines.append(f"  - {claim[:120]}")
            lines.append("")

        if response_score.reasoning:
            lines.append(f"Assessment: {response_score.reasoning[:300]}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _average_claim_confidence(scores: list[ClaimScore]) -> float:
    if not scores:
        return 0.0
    return round(sum(s.confidence for s in scores) / len(scores), 3)


def _weakest(scores: list[ClaimScore], n: int) -> list[str]:
    sorted_scores = sorted(scores, key=lambda s: s.confidence)
    return [s.claim for s in sorted_scores[:n]]


def _strongest(scores: list[ClaimScore], n: int) -> list[str]:
    sorted_scores = sorted(scores, key=lambda s: s.confidence, reverse=True)
    return [s.claim for s in sorted_scores[:n]]


def _clean_str_list(raw: Any, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw[:limit]:
        text = str(item or "").strip()
        if text:
            result.append(text[:200])
    return result
