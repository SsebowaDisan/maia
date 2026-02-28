from __future__ import annotations

import re
from typing import Any

from .models import AnswerBuildContext
from ..text_helpers import compact

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(str(text or "")) if len(match.group(0)) >= 4}


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _evidence_url_by_source(evidence_units: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for unit in evidence_units:
        source = " ".join(str(unit.get("source") or "").split()).strip()
        url = " ".join(str(unit.get("url") or "").split()).strip()
        if not source or not url:
            continue
        if source not in mapping:
            mapping[source] = url
    return mapping


def append_evidence_backed_value_add(lines: list[str], ctx: AnswerBuildContext) -> None:
    report = ctx.verification_report
    if not isinstance(report, dict):
        return
    claim_assessments = report.get("claim_assessments")
    if not isinstance(claim_assessments, list) or not claim_assessments:
        return
    contradictions = report.get("contradictions")
    contradiction_count = len(contradictions) if isinstance(contradictions, list) else 0
    supported = [
        item for item in claim_assessments if isinstance(item, dict) and bool(item.get("supported"))
    ]
    support_ratio = len(supported) / float(max(1, len(claim_assessments)))
    if support_ratio < 0.6 or contradiction_count > 0:
        return

    evidence_units = report.get("evidence_units")
    evidence_by_source = _evidence_url_by_source(evidence_units if isinstance(evidence_units, list) else [])
    request_tokens = _tokenize(ctx.request.message)
    recommendations: list[dict[str, Any]] = []
    for item in supported:
        claim = " ".join(str(item.get("claim") or "").split()).strip()
        source = " ".join(str(item.get("evidence_source") or "").split()).strip()
        if not claim:
            continue
        try:
            confidence_score = max(0.0, min(1.0, float(item.get("score") or 0.0)))
        except Exception:
            confidence_score = 0.0
        claim_tokens = _tokenize(claim)
        relevance = (
            len(claim_tokens.intersection(request_tokens)) / float(max(1, len(claim_tokens)))
            if claim_tokens
            else 0.0
        )
        rank_score = round((0.7 * confidence_score) + (0.3 * relevance), 3)
        recommendations.append(
            {
                "claim": claim,
                "rank_score": rank_score,
                "confidence_score": confidence_score,
                "confidence_label": _confidence_label(confidence_score),
                "source": source or "Verified source",
                "url": evidence_by_source.get(source, ""),
            }
        )
    if not recommendations:
        return
    recommendations.sort(key=lambda row: row["rank_score"], reverse=True)

    lines.append("")
    lines.append("## Evidence-Backed Value Add")
    for row in recommendations[:3]:
        citation = row["url"] or row["source"]
        lines.append(
            "- "
            + compact(str(row["claim"]), 180)
            + f" (confidence: {row['confidence_label']} {row['confidence_score']:.2f}; relevance rank: {row['rank_score']:.2f}). "
            + f"Source: {citation}"
        )
