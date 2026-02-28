from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value


def _normalize_candidate_steps(raw_steps: list[str] | None, *, limit: int = 24) -> list[str]:
    if not isinstance(raw_steps, list):
        return []
    steps: list[str] = []
    for row in raw_steps:
        text = " ".join(str(row or "").split()).strip()
        if not text or text in steps:
            continue
        steps.append(text[:280])
        if len(steps) >= max(1, int(limit)):
            break
    return steps


def _tokenize_for_similarity(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {token for token in tokens if len(token) >= 3}


def _semantic_overlap(left: str, right: str) -> float:
    left_tokens = _tokenize_for_similarity(left)
    right_tokens = _tokenize_for_similarity(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens.intersection(right_tokens)
    union = left_tokens.union(right_tokens)
    return len(intersection) / float(max(1, len(union)))


def curate_next_steps_for_task(
    *,
    request_message: str,
    task_contract: dict[str, Any] | None,
    candidate_steps: list[str],
    executed_steps: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    max_items: int = 8,
) -> list[str]:
    """Select follow-up recommendations without repeating primary task deliverables."""
    normalized_candidates = _normalize_candidate_steps(candidate_steps, limit=28)
    if not normalized_candidates:
        return []

    blocked_phrases: list[str] = []
    if isinstance(task_contract, dict):
        for key in ("objective", "delivery_target"):
            value = " ".join(str(task_contract.get(key) or "").split()).strip()
            if value:
                blocked_phrases.append(value)
        for key in ("required_outputs", "required_facts", "required_actions"):
            rows = task_contract.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                value = " ".join(str(row or "").split()).strip()
                if value:
                    blocked_phrases.append(value)
    request_text = " ".join(str(request_message or "").split()).strip()
    if request_text:
        blocked_phrases.append(request_text)

    completed_phrases = [
        " ".join(str(row.get("title") or "").split()).strip()
        for row in executed_steps
        if isinstance(row, dict) and str(row.get("status") or "").strip().lower() == "success"
    ]
    blocked_phrases.extend([row for row in completed_phrases if row])

    def _is_task_restatement(step: str) -> bool:
        normalized_step = " ".join(str(step or "").split()).strip().lower()
        if not normalized_step:
            return True
        for phrase in blocked_phrases:
            normalized_phrase = " ".join(str(phrase or "").split()).strip().lower()
            if not normalized_phrase:
                continue
            if normalized_step == normalized_phrase:
                return True
            if len(normalized_step) >= 32 and normalized_step in normalized_phrase:
                return True
            if len(normalized_phrase) >= 32 and normalized_phrase in normalized_step:
                return True
            if _semantic_overlap(normalized_step, normalized_phrase) >= 0.35:
                return True
        return False

    heuristic_filtered = [
        step for step in normalized_candidates if not _is_task_restatement(step)
    ]

    if not env_bool("MAIA_AGENT_LLM_NEXT_STEPS_ENABLED", default=True):
        return heuristic_filtered[: max(1, int(max_items))]

    payload = {
        "request_message": request_text,
        "task_contract": sanitize_json_value(task_contract or {}),
        "candidate_steps": heuristic_filtered,
        "executed_steps": sanitize_json_value(executed_steps[-20:]),
        "actions": sanitize_json_value(actions[-20:]),
        "max_items": max(1, min(int(max_items), 10)),
    }
    prompt = (
        "Select follow-up recommendations for this run.\n"
        "Return JSON only:\n"
        '{ "next_steps": ["..."] }\n'
        "Rules:\n"
        "- Keep only post-run follow-up actions.\n"
        "- NEVER restate the original requested deliverables.\n"
        "- NEVER restate already-completed primary actions.\n"
        "- Prioritize unresolved blockers and verification gaps.\n"
        "- Keep each step concise (max 170 chars).\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You curate execution follow-up steps for enterprise agents. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=320,
    )
    if not isinstance(response, dict):
        return heuristic_filtered[: max(1, int(max_items))]

    llm_steps = _normalize_candidate_steps(response.get("next_steps"), limit=max_items)
    if not llm_steps:
        return heuristic_filtered[: max(1, int(max_items))]
    return [step for step in llm_steps if not _is_task_restatement(step)][
        : max(1, int(max_items))
    ]
