from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value
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


def extract_claims_llm(
    *,
    text: str,
    max_claims: int = 8,
) -> list[dict[str, Any]]:
    """Extract factual claims from text using an LLM.

    Returns a list of {claim, corroboration_score, source_diversity_score} dicts.
    Falls back to empty list if LLM is disabled or call fails.
    """
    if not env_bool("MAIA_AGENT_LLM_CLAIM_EXTRACTION_ENABLED", default=True):
        return []
    text_snippet = compact(text, 1200)
    if not text_snippet:
        return []
    cap = max(1, min(int(max_claims), 12))
    payload = {"text": text_snippet, "max_claims": cap}
    response = call_json_response(
        system_prompt=(
            "You extract verifiable factual claims from business research text. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only with this schema:\n"
            '{"claims": [{"claim": "...", "corroboration_score": 0.0, "source_diversity_score": 0.0}]}\n'
            "Rules:\n"
            f"- Extract up to {cap} specific, verifiable claims.\n"
            "- corroboration_score: 0.0-1.0 (how well the claim is supported by multiple sources in the text)\n"
            "- source_diversity_score: 0.0-1.0 (how many distinct sources mention this claim)\n"
            "- Claims must be concrete and falsifiable, not opinions.\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=14,
        max_tokens=640,
    )
    normalized = sanitize_json_value(response) if isinstance(response, dict) else {}
    if not isinstance(normalized, dict):
        return []
    raw_claims = normalized.get("claims")
    if not isinstance(raw_claims, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw_claims[:cap]:
        if not isinstance(item, dict):
            continue
        claim_text = str(item.get("claim") or "").strip()
        if not claim_text:
            continue
        try:
            corr = float(item.get("corroboration_score") or 0.0)
        except Exception:
            corr = 0.0
        try:
            div = float(item.get("source_diversity_score") or 0.0)
        except Exception:
            div = 0.0
        result.append({
            "claim": claim_text,
            "corroboration_score": max(0.0, min(1.0, corr)),
            "source_diversity_score": max(0.0, min(1.0, div)),
        })
    return result
