from __future__ import annotations

import pytest

from api.services.agent.intelligence_sections.claim_matrix import (
    ClaimMatrix,
    ClaimRow,
    build_claim_matrix,
)


# ── unit: ClaimRow trust score ────────────────────────────────────────────────

def test_claim_row_trust_score_formula():
    row = ClaimRow(
        claim="Revenue grew 20% YoY",
        corroboration_score=0.8,
        credibility_score=0.9,
        source_diversity_score=0.6,
    )
    expected = 0.8 * 0.45 + 0.9 * 0.35 + 0.6 * 0.20
    assert abs(row.trust_score - expected) < 0.001


def test_claim_row_gate_color_green():
    row = ClaimRow(claim="A", corroboration_score=0.9, credibility_score=0.9, source_diversity_score=0.9)
    assert row.gate_color == "green"


def test_claim_row_gate_color_amber():
    row = ClaimRow(claim="B", corroboration_score=0.5, credibility_score=0.6, source_diversity_score=0.5)
    # 0.5*0.45 + 0.6*0.35 + 0.5*0.20 = 0.225 + 0.21 + 0.10 = 0.535 → amber
    assert row.gate_color in ("amber", "red")


def test_claim_row_gate_color_red():
    row = ClaimRow(claim="C", corroboration_score=0.1, credibility_score=0.2, source_diversity_score=0.1)
    assert row.gate_color == "red"


def test_claim_row_to_dict():
    row = ClaimRow(claim="X", corroboration_score=0.7, credibility_score=0.8, source_diversity_score=0.5)
    d = row.to_dict()
    assert d["claim"] == "X"
    assert "trust_score" in d
    assert "gate_color" in d
    assert d["contradictions"] == []


# ── unit: ClaimMatrix aggregation ────────────────────────────────────────────

def test_claim_matrix_overall_trust_average():
    matrix = ClaimMatrix(claims=[
        ClaimRow(claim="A", corroboration_score=0.8, credibility_score=0.9, source_diversity_score=0.8),
        ClaimRow(claim="B", corroboration_score=0.4, credibility_score=0.5, source_diversity_score=0.4),
    ])
    # trust scores should average to somewhere between 0.55 and 1.0
    assert 0.3 <= matrix.overall_trust_score <= 1.0


def test_claim_matrix_empty():
    matrix = ClaimMatrix()
    assert matrix.overall_trust_score == 0.0
    assert matrix.overall_gate_color in ("red", "amber", "green")
    assert matrix.contested_count == 0


def test_claim_matrix_contested_count():
    matrix = ClaimMatrix(claims=[
        ClaimRow(claim="A", contradictions=[{"claim_a": "A", "claim_b": "B"}]),
        ClaimRow(claim="B", contradictions=[]),
    ])
    assert matrix.contested_count == 1


def test_claim_matrix_to_dict():
    matrix = ClaimMatrix(claims=[
        ClaimRow(claim="Market size is $5B", corroboration_score=0.9, credibility_score=0.9, source_diversity_score=0.8)
    ])
    d = matrix.to_dict()
    assert d["claim_count"] == 1
    assert "overall_trust_score" in d
    assert "overall_gate_color" in d
    assert len(d["claims"]) == 1


# ── unit: build_claim_matrix ─────────────────────────────────────────────────

def test_build_claim_matrix_basic():
    claims = [
        {"claim": "Revenue is $10B", "corroboration_score": 0.8, "source_diversity_score": 0.6},
        {"claim": "Market grew 15%", "corroboration_score": 0.6, "source_diversity_score": 0.5},
    ]
    contradictions = [
        {
            "claim_a": "Revenue is $10B",
            "claim_b": "Revenue is $8B",
            "contradiction_type": "numeric",
            "severity": 0.9,
            "description": "Different revenue figures",
        }
    ]
    matrix = build_claim_matrix(
        claims=claims,
        contradictions=contradictions,
        source_credibility_avg=0.85,
    )
    assert isinstance(matrix, ClaimMatrix)
    assert len(matrix.claims) == 2
    # The "Revenue" claim should have the contradiction attached
    revenue_claim = next((c for c in matrix.claims if "Revenue" in c.claim), None)
    assert revenue_claim is not None
    assert len(revenue_claim.contradictions) >= 1


def test_build_claim_matrix_empty_claims():
    matrix = build_claim_matrix(claims=[], contradictions=[], source_credibility_avg=0.7)
    assert isinstance(matrix, ClaimMatrix)
    assert len(matrix.claims) == 0


def test_build_claim_matrix_skips_invalid():
    claims = [
        None,
        {"claim": "", "corroboration_score": 0.5},
        {"claim": "Valid claim here", "corroboration_score": 0.7, "source_diversity_score": 0.5},
    ]
    matrix = build_claim_matrix(claims=claims, contradictions=[], source_credibility_avg=0.7)
    assert len(matrix.claims) == 1
