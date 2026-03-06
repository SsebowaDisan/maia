from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


def _clean_rows(rows: list[Any], *, limit: int = 8) -> list[str]:
    output: list[str] = []
    for item in rows:
        text = _clean_text(item)
        if not text or text in output:
            continue
        output.append(text)
        if len(output) >= max(1, int(limit)):
            break
    return output


def _fallback_slots(requirements: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "requirement": requirement,
            "description": requirement,
            "discoverable": False,
            "blocking": True,
            "confidence": 0.5,
            "evidence_sources": [],
            "resolved_value": "",
            "question": f"Please provide: {requirement}",
        }
        for requirement in requirements[:8]
    ]


def classify_missing_requirement_slots(
    *,
    missing_requirements: list[str],
    message: str,
    agent_goal: str,
    rewritten_task: str,
    intent_tags: list[str],
    conversation_summary: str = "",
) -> list[dict[str, Any]]:
    requirements = _clean_rows(list(missing_requirements or []), limit=8)
    if not requirements:
        return []
    if not env_bool("MAIA_AGENT_LLM_CONTRACT_SLOT_ENABLED", default=True):
        return _fallback_slots(requirements)

    payload = {
        "requirements": requirements,
        "message": _clean_text(message, limit=500),
        "agent_goal": _clean_text(agent_goal, limit=360),
        "rewritten_task": _clean_text(rewritten_task, limit=500),
        "intent_tags": _clean_rows(list(intent_tags or []), limit=10),
        "conversation_summary": _clean_text(conversation_summary, limit=360),
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You are a contract-slot classifier for an autonomous execution agent. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Classify each missing requirement into execution slots.\n"
                "Return JSON only:\n"
                '{ "slots":[{'
                '"requirement_index":0,'
                '"description":"string",'
                '"discoverable":true,'
                '"blocking":true,'
                '"confidence":0.0,'
                '"evidence_sources":["website","search","documents"],'
                '"resolved_value":"",'
                '"question":"string"'
                "}]} \n"
                "Rules:\n"
                "- Use semantic reasoning, not keyword matching.\n"
                "- discoverable=true if the agent can likely find it via browsing/search/documents.\n"
                "- blocking=true only if execution cannot proceed responsibly without it.\n"
                "- Keep confidence in [0,1].\n"
                "- question must be concise and user-ready.\n"
                "- Use only requirement_index values from the provided list.\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=520,
        )
    except Exception:
        return _fallback_slots(requirements)
    if not isinstance(response, dict):
        return _fallback_slots(requirements)
    raw_slots = response.get("slots")
    if not isinstance(raw_slots, list):
        return _fallback_slots(requirements)

    slots: list[dict[str, Any]] = []
    for raw in raw_slots[:16]:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get("requirement_index"))
        except Exception:
            continue
        if index < 0 or index >= len(requirements):
            continue
        requirement = requirements[index]
        confidence_raw = raw.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except Exception:
            confidence = 0.5
        evidence_sources = raw.get("evidence_sources")
        clean_sources = (
            _clean_rows(evidence_sources, limit=6) if isinstance(evidence_sources, list) else []
        )
        slot = {
            "requirement": requirement,
            "description": _clean_text(raw.get("description"), limit=240) or requirement,
            "discoverable": bool(raw.get("discoverable")),
            "blocking": bool(raw.get("blocking")),
            "confidence": confidence,
            "evidence_sources": clean_sources,
            "resolved_value": _clean_text(raw.get("resolved_value"), limit=240),
            "question": _clean_text(raw.get("question"), limit=240) or f"Please provide: {requirement}",
        }
        if slot in slots:
            continue
        slots.append(slot)
    if not slots:
        return _fallback_slots(requirements)
    requirement_rows = {slot.get("requirement") for slot in slots}
    for requirement in requirements:
        if requirement in requirement_rows:
            continue
        slots.append(
            {
                "requirement": requirement,
                "description": requirement,
                "discoverable": False,
                "blocking": True,
                "confidence": 0.5,
                "evidence_sources": [],
                "resolved_value": "",
                "question": f"Please provide: {requirement}",
            }
        )
    return slots[:8]

