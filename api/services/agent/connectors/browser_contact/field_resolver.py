from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

CONTACT_INTENTS: tuple[str, ...] = (
    "name",
    "email",
    "phone",
    "company",
    "subject",
    "message",
)
_INTENT_SET = set(CONTACT_INTENTS)


def _clean_text(value: Any, *, limit: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


def build_intent_values(
    *,
    sender_name: str,
    sender_email: str,
    sender_company: str,
    sender_phone: str,
    subject: str,
    message: str,
) -> dict[str, str]:
    return {
        "name": _clean_text(sender_name, limit=140),
        "email": _clean_text(sender_email, limit=180),
        "company": _clean_text(sender_company, limit=140),
        "phone": _clean_text(sender_phone, limit=64),
        "subject": _clean_text(subject, limit=180),
        "message": _clean_text(message, limit=900),
    }


def _parse_confidence(value: Any, *, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        token = str(value or "").strip().lower()
        if token in {"very_high", "very-high", "very high"}:
            return 0.95
        if token == "high":
            return 0.9
        if token in {"medium", "med", "moderate"}:
            return 0.7
        if token in {"low", "weak"}:
            return 0.45
        return max(0.0, min(1.0, float(default)))


def _compact_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for index, field in enumerate(fields[:32]):
        if not isinstance(field, dict):
            continue
        compact.append(
            {
                "field_index": index,
                "dom_index": int(field.get("dom_index") or index),
                "tag": _clean_text(field.get("tag"), limit=24).lower(),
                "input_type": _clean_text(field.get("input_type"), limit=24).lower(),
                "label": _clean_text(field.get("label"), limit=160),
                "placeholder": _clean_text(field.get("placeholder"), limit=160),
                "aria_label": _clean_text(field.get("aria_label"), limit=160),
                "field_name": _clean_text(field.get("field_name"), limit=120),
                "field_id": _clean_text(field.get("field_id"), limit=120),
                "autocomplete": _clean_text(field.get("autocomplete"), limit=64).lower(),
                "required": bool(field.get("required")),
            }
        )
    return compact


def parse_llm_mappings(
    *,
    payload: dict[str, Any] | None,
    fields: list[dict[str, Any]],
    values: dict[str, str],
    minimum_confidence: float,
) -> list[dict[str, Any]]:
    rows = payload.get("mappings") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    best_by_field: dict[int, dict[str, Any]] = {}
    for entry in rows[:48]:
        if not isinstance(entry, dict):
            continue
        try:
            field_index = int(entry.get("field_index"))
        except Exception:
            continue
        if field_index < 0 or field_index >= len(fields):
            continue
        intent = _clean_text(entry.get("intent"), limit=32).lower()
        if intent not in _INTENT_SET:
            continue
        value = _clean_text(values.get(intent), limit=900)
        if not value:
            continue
        confidence = _parse_confidence(entry.get("confidence"), default=0.0)
        if confidence < max(0.0, min(1.0, float(minimum_confidence))):
            continue
        current = best_by_field.get(field_index)
        if current and float(current.get("confidence") or 0.0) >= confidence:
            continue
        best_by_field[field_index] = {
            "field_index": field_index,
            "intent": intent,
            "value": value,
            "confidence": confidence,
            "reason": _clean_text(entry.get("reason"), limit=220),
        }
    return [best_by_field[index] for index in sorted(best_by_field.keys())]


def _semantic_fallback_mappings(
    *,
    fields: list[dict[str, Any]],
    values: dict[str, str],
    minimum_confidence: float,
) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    used_fields: set[int] = set()
    threshold = max(0.0, min(1.0, float(minimum_confidence)))
    for index, field in enumerate(fields[:32]):
        tag = _clean_text(field.get("tag"), limit=24).lower()
        input_type = _clean_text(field.get("input_type"), limit=24).lower()
        autocomplete = _clean_text(field.get("autocomplete"), limit=64).lower()
        intent = ""
        if input_type == "email" or autocomplete == "email":
            intent = "email"
        elif input_type == "tel" or autocomplete in {"tel", "tel-national"}:
            intent = "phone"
        elif autocomplete in {"name", "given-name", "family-name"}:
            intent = "name"
        elif tag == "textarea":
            intent = "message"
        if not intent:
            continue
        value = _clean_text(values.get(intent), limit=900)
        if not value:
            continue
        confidence = 0.72
        if confidence < threshold:
            continue
        if index in used_fields:
            continue
        used_fields.add(index)
        mappings.append(
            {
                "field_index": index,
                "intent": intent,
                "value": value,
                "confidence": confidence,
                "reason": "semantic_fallback",
            }
        )
    return mappings


def resolve_field_mappings_with_llm(
    *,
    fields: list[dict[str, Any]],
    intent_values: dict[str, str],
    minimum_confidence: float = 0.68,
) -> tuple[list[dict[str, Any]], str]:
    if not fields:
        return [], "no fields available"
    available_values = {
        key: _clean_text(value, limit=900)
        for key, value in intent_values.items()
        if key in _INTENT_SET and _clean_text(value, limit=900)
    }
    if not available_values:
        return [], "no values available for mapping"
    compact_fields = _compact_fields(fields)
    if not has_openai_credentials():
        fallback = _semantic_fallback_mappings(
            fields=fields,
            values=available_values,
            minimum_confidence=minimum_confidence,
        )
        return fallback, "OpenAI credentials missing; semantic fallback used"

    payload = {
        "fields": compact_fields,
        "available_values": {key: value[:260] for key, value in available_values.items()},
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You map contact form fields to provided sender values for autonomous execution. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Map fields to intents using semantic understanding.\n"
                "Return JSON only:\n"
                '{ "mappings":[{"field_index":0,"intent":"email","confidence":0.0,"reason":"..."}] }\n'
                "Rules:\n"
                "- Use only field_index values from input.\n"
                "- Allowed intents: name,email,phone,company,subject,message.\n"
                "- Do not fabricate values; map only to provided available_values.\n"
                "- Skip consent, verification, anti-bot, and terms controls.\n"
                "- Keep confidence in [0,1].\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=12,
            max_tokens=520,
        )
    except Exception:
        response = None
    mappings = parse_llm_mappings(
        payload=response if isinstance(response, dict) else None,
        fields=fields,
        values=available_values,
        minimum_confidence=minimum_confidence,
    )
    if mappings:
        return mappings, f"LLM mapped {len(mappings)} field(s)"
    fallback = _semantic_fallback_mappings(
        fields=fields,
        values=available_values,
        minimum_confidence=minimum_confidence,
    )
    if fallback:
        return fallback, f"LLM returned no confident mappings; semantic fallback mapped {len(fallback)} field(s)"
    return [], "No confident field mappings"


def fill_form_field_by_index(
    *,
    form: Any,
    field_index: int,
    value: str,
) -> bool:
    clean_value = _clean_text(value, limit=900)
    if not clean_value:
        return False
    try:
        field = form.locator("input, textarea, select, button").nth(max(0, int(field_index)))
    except Exception:
        return False
    try:
        tag = _clean_text(field.evaluate("el => (el.tagName || '').toLowerCase()"), limit=16).lower()
    except Exception:
        tag = ""
    try:
        field.click(timeout=3000)
    except Exception:
        pass
    try:
        if tag == "select":
            try:
                field.select_option(label=clean_value, timeout=3500)
                return True
            except Exception:
                field.select_option(value=clean_value, timeout=3500)
                return True
        field.fill(clean_value, timeout=4000)
        return True
    except Exception:
        return False
