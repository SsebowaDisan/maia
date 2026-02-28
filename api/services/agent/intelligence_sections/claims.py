from __future__ import annotations

import re
from typing import Any

from api.services.agent.models import AgentAction

from .text_utils import compact, tokenize


def extract_claim_candidates(
    *,
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    limit: int = 8,
) -> list[str]:
    text_blocks: list[str] = []
    for row in executed_steps:
        if str(row.get("status") or "") != "success":
            continue
        summary = str(row.get("summary") or "").strip()
        title = str(row.get("title") or "").strip()
        if summary:
            text_blocks.append(f"{title}. {summary}" if title else summary)
    for action in actions:
        if action.status != "success":
            continue
        if action.summary.strip():
            text_blocks.append(action.summary.strip())
    combined = "\n".join(text_blocks)
    fragments = re.split(r"[.\n;!?]+", combined)
    claims: list[str] = []
    seen: set[str] = set()
    for raw in fragments:
        claim = " ".join(raw.split()).strip()
        if len(claim) < 24:
            continue
        tokens = tokenize(claim)
        if len(tokens) < 4:
            continue
        key = claim.lower()
        if key in seen:
            continue
        seen.add(key)
        claims.append(compact(claim, 240))
        if len(claims) >= limit:
            break
    return claims


def score_claim_support(
    *,
    claim: str,
    evidence_units: list[dict[str, str]],
) -> dict[str, Any]:
    claim_tokens = tokenize(claim)
    if not claim_tokens:
        return {
            "claim": claim,
            "supported": False,
            "score": 0.0,
            "evidence_source": "",
            "evidence_excerpt": "",
        }
    best_score = 0.0
    best_source = ""
    best_excerpt = ""
    for evidence in evidence_units:
        evidence_text = str(evidence.get("text") or "")
        if not evidence_text:
            continue
        evidence_tokens = tokenize(evidence_text)
        if not evidence_tokens:
            continue
        overlap = len(claim_tokens.intersection(evidence_tokens))
        score = overlap / float(max(1, len(claim_tokens)))
        if score > best_score:
            best_score = score
            best_source = str(evidence.get("source") or "")
            best_excerpt = compact(evidence_text, 200)
    supported = best_score >= 0.22
    return {
        "claim": claim,
        "supported": supported,
        "score": round(best_score, 3),
        "evidence_source": best_source,
        "evidence_excerpt": best_excerpt,
    }
