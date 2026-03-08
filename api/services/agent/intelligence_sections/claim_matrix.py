from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Trust score weights (must sum to 1.0)
_W_CORROBORATION = 0.45
_W_CREDIBILITY = 0.35
_W_DIVERSITY = 0.20


@dataclass
class ClaimRow:
    """A single claim with its support metrics."""
    claim: str
    corroboration_score: float = 0.0   # how many sources agree
    credibility_score: float = 0.62    # avg credibility of supporting sources
    source_diversity_score: float = 0.0  # how many distinct domains mention it
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    resolution: dict[str, Any] = field(default_factory=dict)

    @property
    def trust_score(self) -> float:
        """Composite trust: corroboration×0.45 + credibility×0.35 + diversity×0.20."""
        raw = (
            _W_CORROBORATION * self.corroboration_score
            + _W_CREDIBILITY * self.credibility_score
            + _W_DIVERSITY * self.source_diversity_score
        )
        return max(0.0, min(1.0, raw))

    @property
    def gate_color(self) -> str:
        """3-color trust gate: green (≥0.80) / amber (≥0.55) / red (<0.55)."""
        score = self.trust_score
        if score >= 0.80:
            return "green"
        if score >= 0.55:
            return "amber"
        return "red"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "corroboration_score": round(self.corroboration_score, 3),
            "credibility_score": round(self.credibility_score, 3),
            "source_diversity_score": round(self.source_diversity_score, 3),
            "trust_score": round(self.trust_score, 3),
            "gate_color": self.gate_color,
            "contradictions": self.contradictions,
            "resolution": self.resolution,
        }


@dataclass
class ClaimMatrix:
    """A matrix of extracted claims with trust scores and contradiction analysis."""
    claims: list[ClaimRow] = field(default_factory=list)

    @property
    def overall_trust_score(self) -> float:
        """Average trust score across all claims. 0.0 if no claims."""
        if not self.claims:
            return 0.0
        return sum(c.trust_score for c in self.claims) / len(self.claims)

    @property
    def overall_gate_color(self) -> str:
        score = self.overall_trust_score
        if score >= 0.80:
            return "green"
        if score >= 0.55:
            return "amber"
        return "red"

    @property
    def contested_count(self) -> int:
        return sum(1 for c in self.claims if c.contradictions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_trust_score": round(self.overall_trust_score, 3),
            "overall_gate_color": self.overall_gate_color,
            "claim_count": len(self.claims),
            "contested_count": self.contested_count,
            "claims": [c.to_dict() for c in self.claims],
        }


def build_claim_matrix(
    *,
    claims: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    source_credibility_avg: float = 0.62,
) -> ClaimMatrix:
    """Build a ClaimMatrix from extracted claims and contradiction lists.

    Args:
        claims: from extract_claims_llm() — each has {claim, corroboration_score, source_diversity_score}
        contradictions: from detect_contradictions_llm() — each has {claim_a, claim_b, severity, ...}
        source_credibility_avg: average credibility score of sources used in research
    """
    rows: list[ClaimRow] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        claim_text = str(item.get("claim") or "").strip()
        if not claim_text:
            continue
        # Find contradictions that involve this claim
        claim_contras = [
            c for c in contradictions
            if isinstance(c, dict) and (
                claim_text[:60] in str(c.get("claim_a") or "")
                or claim_text[:60] in str(c.get("claim_b") or "")
            )
        ]
        try:
            corroboration = float(item.get("corroboration_score") or 0.0)
        except Exception:
            corroboration = 0.0
        try:
            diversity = float(item.get("source_diversity_score") or 0.0)
        except Exception:
            diversity = 0.0
        rows.append(ClaimRow(
            claim=claim_text,
            corroboration_score=max(0.0, min(1.0, corroboration)),
            credibility_score=max(0.0, min(1.0, source_credibility_avg)),
            source_diversity_score=max(0.0, min(1.0, diversity)),
            contradictions=claim_contras,
        ))
    return ClaimMatrix(claims=rows)


__all__ = ["ClaimRow", "ClaimMatrix", "build_claim_matrix"]
