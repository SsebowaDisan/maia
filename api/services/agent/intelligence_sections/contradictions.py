from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

from .constants import NUMBER_RE
from .text_utils import compact, contains_negation, tokenize


def detect_potential_contradictions(evidence_units: list[dict[str, str]]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    limited = evidence_units[:12]
    for left_idx in range(len(limited)):
        left = limited[left_idx]
        left_text = str(left.get("text") or "")
        left_tokens = tokenize(left_text)
        if len(left_tokens) < 4:
            continue
        left_numbers = NUMBER_RE.findall(left_text)
        left_negation = contains_negation(left_text)
        for right_idx in range(left_idx + 1, len(limited)):
            right = limited[right_idx]
            right_text = str(right.get("text") or "")
            right_tokens = tokenize(right_text)
            if len(right_tokens) < 4:
                continue
            overlap = left_tokens.intersection(right_tokens)
            if len(overlap) < 4:
                continue
            right_numbers = NUMBER_RE.findall(right_text)
            right_negation = contains_negation(right_text)
            contradiction_reason = ""
            if left_negation != right_negation and len(overlap) >= 5:
                contradiction_reason = "negation_mismatch"
            elif left_numbers and right_numbers and left_numbers[0] != right_numbers[0] and len(overlap) >= 5:
                contradiction_reason = "numeric_mismatch"
            if not contradiction_reason:
                continue
            contradictions.append(
                {
                    "type": contradiction_reason,
                    "left_source": str(left.get("source") or ""),
                    "right_source": str(right.get("source") or ""),
                    "overlap_terms": sorted(list(overlap))[:8],
                    "left_excerpt": compact(left_text, 180),
                    "right_excerpt": compact(right_text, 180),
                }
            )
            if len(contradictions) >= 6:
                return contradictions
    return contradictions


def detect_contradictions_llm(
    *,
    claims: list[dict[str, Any]],
    max_contradictions: int = 4,
) -> list[dict[str, Any]]:
    """Detect contradictions between claims using an LLM.

    Input: list of {claim, corroboration_score, ...} from extract_claims_llm().
    Returns: list of {claim_a, claim_b, contradiction_type, severity, description}.
    """
    if not env_bool("MAIA_AGENT_LLM_CONTRADICTION_DETECTION_ENABLED", default=True):
        return []
    if len(claims) < 2:
        return []
    cap = max(1, min(int(max_contradictions), 6))
    claim_texts = [str(c.get("claim") or "") for c in claims[:12] if c.get("claim")]
    if len(claim_texts) < 2:
        return []
    payload = {"claims": claim_texts, "max_contradictions": cap}
    response = call_json_response(
        system_prompt=(
            "You detect factual contradictions between business intelligence claims. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only with this schema:\n"
            '{"contradictions": [{"claim_a": "...", "claim_b": "...", '
            '"contradiction_type": "numeric|factual|temporal|negation", '
            '"severity": 0.0, "description": "..."}]}\n'
            "Rules:\n"
            f"- Identify up to {cap} genuine factual contradictions.\n"
            "- severity: 0.0-1.0 (1.0 = directly contradictory)\n"
            "- Only report contradictions where both claims cannot be simultaneously true.\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=14,
        max_tokens=640,
    )
    normalized = sanitize_json_value(response) if isinstance(response, dict) else {}
    if not isinstance(normalized, dict):
        return []
    raw = normalized.get("contradictions")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[:cap]:
        if not isinstance(item, dict):
            continue
        claim_a = str(item.get("claim_a") or "").strip()
        claim_b = str(item.get("claim_b") or "").strip()
        if not claim_a or not claim_b:
            continue
        try:
            severity = float(item.get("severity") or 0.5)
        except Exception:
            severity = 0.5
        result.append({
            "claim_a": claim_a,
            "claim_b": claim_b,
            "contradiction_type": str(item.get("contradiction_type") or "factual").strip(),
            "severity": max(0.0, min(1.0, severity)),
            "description": compact(str(item.get("description") or ""), 200),
        })
    return result


def resolve_contradiction_llm(
    *,
    claim_a: str,
    claim_b: str,
    context: str = "",
) -> dict[str, Any]:
    """Ask an LLM to resolve a contradiction between two claims.

    Returns: {resolution, preferred_claim, confidence, reasoning}.
    """
    if not env_bool("MAIA_AGENT_LLM_CONTRADICTION_RESOLUTION_ENABLED", default=True):
        return {"resolution": "unresolved", "preferred_claim": "", "confidence": 0.0, "reasoning": ""}
    payload = {
        "claim_a": compact(claim_a, 300),
        "claim_b": compact(claim_b, 300),
        "context": compact(context, 400),
    }
    response = call_json_response(
        system_prompt=(
            "You resolve factual contradictions in business intelligence research. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only with this schema:\n"
            '{"resolution": "claim_a|claim_b|both_partial|unresolvable", '
            '"preferred_claim": "...", "confidence": 0.0, "reasoning": "..."}\n'
            "Rules:\n"
            "- resolution: which claim is more likely correct, or if both are partially right.\n"
            "- preferred_claim: the more accurate version of the claim (or empty if unresolvable).\n"
            "- confidence: 0.0-1.0 in your resolution.\n"
            "- reasoning: brief explanation (max 120 chars).\n\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=320,
    )
    normalized = sanitize_json_value(response) if isinstance(response, dict) else {}
    if not isinstance(normalized, dict):
        return {"resolution": "unresolved", "preferred_claim": "", "confidence": 0.0, "reasoning": ""}
    try:
        confidence = float(normalized.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    return {
        "resolution": str(normalized.get("resolution") or "unresolved").strip(),
        "preferred_claim": compact(str(normalized.get("preferred_claim") or ""), 300),
        "confidence": max(0.0, min(1.0, confidence)),
        "reasoning": compact(str(normalized.get("reasoning") or ""), 120),
    }
