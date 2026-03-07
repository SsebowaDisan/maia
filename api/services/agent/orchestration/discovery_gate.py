from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

_ALLOWED_SLOT_STATES = {"open", "attempting_discovery", "resolved", "blocked"}


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


def _clean_rows(rows: list[Any], *, limit: int = 8) -> list[str]:
    output: list[str] = []
    for row in rows:
        text = _clean_text(row)
        if not text or text in output:
            continue
        output.append(text)
        if len(output) >= max(1, int(limit)):
            break
    return output


def with_slot_lifecycle_defaults(
    *,
    slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in slots[:24]:
        if not isinstance(row, dict):
            continue
        slot = dict(row)
        resolved_value = _clean_text(slot.get("resolved_value"), limit=240)
        state = _clean_text(slot.get("state"), limit=48).lower()
        if state not in _ALLOWED_SLOT_STATES:
            state = "resolved" if resolved_value else "open"
        try:
            attempt_count = max(0, int(slot.get("attempt_count") or 0))
        except Exception:
            attempt_count = 0
        evidence_sources = (
            _clean_rows(slot.get("evidence_sources"), limit=8)
            if isinstance(slot.get("evidence_sources"), list)
            else []
        )
        slot["state"] = state
        slot["attempt_count"] = attempt_count
        slot["resolved_value"] = resolved_value
        slot["evidence_sources"] = evidence_sources
        slot["state_reason"] = _clean_text(slot.get("state_reason"), limit=260)
        normalized.append(slot)
    return normalized


def _fallback_lifecycle_update(
    *,
    slots: list[dict[str, Any]],
    unresolved_requirements: list[str],
    attempted_requirements: list[str],
    evidence_sources: list[str],
) -> list[dict[str, Any]]:
    unresolved = {
        _clean_text(item).lower()
        for item in unresolved_requirements
        if _clean_text(item)
    }
    attempted = {
        _clean_text(item).lower()
        for item in attempted_requirements
        if _clean_text(item)
    }
    updated: list[dict[str, Any]] = []
    for slot in with_slot_lifecycle_defaults(slots=slots):
        requirement = _clean_text(slot.get("requirement"), limit=240).lower()
        if not requirement:
            updated.append(slot)
            continue
        sources = _clean_rows(
            [
                *(
                    slot.get("evidence_sources")
                    if isinstance(slot.get("evidence_sources"), list)
                    else []
                ),
                *evidence_sources,
            ],
            limit=10,
        )
        slot["evidence_sources"] = sources
        if requirement in attempted:
            slot["attempt_count"] = int(slot.get("attempt_count") or 0) + 1

        resolved_value = _clean_text(slot.get("resolved_value"), limit=240)
        if resolved_value:
            slot["state"] = "resolved"
            slot["state_reason"] = "Resolved from discovered or provided value."
            updated.append(slot)
            continue

        if requirement in unresolved:
            if bool(slot.get("discoverable")) and requirement in attempted:
                slot["state"] = "attempting_discovery"
                slot["state_reason"] = "Autonomous discovery in progress."
            elif bool(slot.get("blocking")):
                slot["state"] = "blocked"
                slot["state_reason"] = "Blocking requirement remains unresolved."
            else:
                slot["state"] = "open"
                slot["state_reason"] = "Optional unresolved requirement."
            updated.append(slot)
            continue

        slot["state"] = "resolved"
        slot["state_reason"] = "No longer unresolved after autonomous checks."
        updated.append(slot)
    return updated


def update_slot_lifecycle(
    *,
    slots: list[dict[str, Any]],
    unresolved_requirements: list[str],
    attempted_requirements: list[str] | None = None,
    evidence_sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_slots = with_slot_lifecycle_defaults(slots=slots)
    if not normalized_slots:
        return []
    unresolved = _clean_rows(unresolved_requirements or [], limit=10)
    attempted = _clean_rows(attempted_requirements or [], limit=10)
    evidence = _clean_rows(evidence_sources or [], limit=8)
    if not env_bool("MAIA_AGENT_LLM_SLOT_LIFECYCLE_ENABLED", default=True):
        return _fallback_lifecycle_update(
            slots=normalized_slots,
            unresolved_requirements=unresolved,
            attempted_requirements=attempted,
            evidence_sources=evidence,
        )

    payload = {
        "slots": [
            {
                "slot_index": index,
                "requirement": _clean_text(slot.get("requirement"), limit=220),
                "description": _clean_text(slot.get("description"), limit=260),
                "discoverable": bool(slot.get("discoverable")),
                "blocking": bool(slot.get("blocking")),
                "confidence": slot.get("confidence"),
                "resolved_value": _clean_text(slot.get("resolved_value"), limit=240),
                "state": _clean_text(slot.get("state"), limit=48).lower(),
                "attempt_count": int(slot.get("attempt_count") or 0),
            }
            for index, slot in enumerate(normalized_slots[:16])
        ],
        "unresolved_requirements": unresolved,
        "attempted_requirements": attempted,
        "evidence_sources": evidence,
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You update slot lifecycle state for an autonomous execution agent. "
                "Use semantic matching and return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only:\n"
                '{ "slots":[{"slot_index":0,"state":"open|attempting_discovery|resolved|blocked",'
                '"state_reason":"string","resolved_value":"string"}] }\n'
                "Rules:\n"
                "- Use semantic understanding of requirement meaning.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- Preserve unresolved blockers as blocked when attempts are exhausted.\n"
                "- Keep state_reason concise.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=520,
        )
    except Exception:
        response = None
    rows = response.get("slots") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return _fallback_lifecycle_update(
            slots=normalized_slots,
            unresolved_requirements=unresolved,
            attempted_requirements=attempted,
            evidence_sources=evidence,
        )

    merged = [dict(slot) for slot in normalized_slots]
    for row in rows[:24]:
        if not isinstance(row, dict):
            continue
        try:
            slot_index = int(row.get("slot_index"))
        except Exception:
            continue
        if slot_index < 0 or slot_index >= len(merged):
            continue
        state = _clean_text(row.get("state"), limit=48).lower()
        if state not in _ALLOWED_SLOT_STATES:
            continue
        slot = dict(merged[slot_index])
        requirement = _clean_text(slot.get("requirement"), limit=220).lower()
        if requirement in {
            _clean_text(item).lower() for item in attempted if _clean_text(item)
        }:
            slot["attempt_count"] = int(slot.get("attempt_count") or 0) + 1
        slot["state"] = state
        slot["state_reason"] = _clean_text(row.get("state_reason"), limit=260)
        resolved_value = _clean_text(row.get("resolved_value"), limit=240)
        if resolved_value:
            slot["resolved_value"] = resolved_value
        slot["evidence_sources"] = _clean_rows(
            [
                *(
                    slot.get("evidence_sources")
                    if isinstance(slot.get("evidence_sources"), list)
                    else []
                ),
                *evidence,
            ],
            limit=10,
        )
        merged[slot_index] = slot
    return merged


def blocking_requirements_from_slots(
    *,
    slots: list[dict[str, Any]],
    fallback_requirements: list[str],
    limit: int = 6,
    discovery_attempts_required: int = 2,
) -> list[str]:
    min_attempts = max(1, int(discovery_attempts_required))
    slot_rows = [row for row in slots[:24] if isinstance(row, dict)]
    if slot_rows:
        candidate_rows: list[str] = []
        for slot in slot_rows:
            requirement = _clean_text(slot.get("requirement"))
            if not requirement:
                continue
            if not bool(slot.get("blocking")):
                continue
            discoverable = bool(slot.get("discoverable"))
            state = _clean_text(slot.get("state"), limit=48).lower()
            try:
                attempt_count = max(0, int(slot.get("attempt_count") or 0))
            except Exception:
                attempt_count = 0
            discovery_exhausted = state == "blocked" or attempt_count >= min_attempts
            if not discoverable or discovery_exhausted:
                candidate_rows.append(requirement)
        return _clean_rows(candidate_rows, limit=limit)

    # Fallback path when no slots were produced: preserve previous behavior.
    return _clean_rows(list(fallback_requirements or []), limit=limit)


def unresolved_requirements_from_slots(
    *,
    slots: list[dict[str, Any]],
    fallback_requirements: list[str],
    limit: int = 8,
) -> list[str]:
    slot_rows = [row for row in slots[:24] if isinstance(row, dict)]
    if not slot_rows:
        return _clean_rows(list(fallback_requirements or []), limit=limit)
    candidate_rows: list[str] = []
    for slot in slot_rows:
        requirement = _clean_text(slot.get("requirement"))
        if not requirement:
            continue
        state = _clean_text(slot.get("state"), limit=48).lower()
        resolved_value = _clean_text(slot.get("resolved_value"), limit=240)
        if resolved_value:
            continue
        if state == "resolved":
            continue
        candidate_rows.append(requirement)
    return _clean_rows(candidate_rows, limit=limit)


def attempted_discovery_requirements_from_slots(
    *,
    slots: list[dict[str, Any]],
    limit: int = 8,
) -> list[str]:
    candidate_rows: list[str] = []
    for slot in slots[:24]:
        if not isinstance(slot, dict):
            continue
        requirement = _clean_text(slot.get("requirement"))
        if not requirement:
            continue
        resolved_value = _clean_text(slot.get("resolved_value"), limit=240)
        if resolved_value:
            continue
        if bool(slot.get("discoverable")):
            candidate_rows.append(requirement)
    return _clean_rows(candidate_rows, limit=limit)


def clarification_questions_from_slots(
    *,
    slots: list[dict[str, Any]],
    requirements: list[str],
    limit: int = 6,
) -> list[str]:
    clean_requirements = _clean_rows(list(requirements or []), limit=limit)
    if not clean_requirements:
        return []
    question_by_requirement: dict[str, str] = {}
    for slot in slots[:24]:
        if not isinstance(slot, dict):
            continue
        requirement = _clean_text(slot.get("requirement"))
        question = _clean_text(slot.get("question"))
        if requirement and question and requirement not in question_by_requirement:
            question_by_requirement[requirement] = question
    questions: list[str] = []
    for requirement in clean_requirements:
        question = question_by_requirement.get(requirement) or f"Please provide: {requirement}"
        if question in questions:
            continue
        questions.append(question)
        if len(questions) >= max(1, int(limit)):
            break
    return questions
