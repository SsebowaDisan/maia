from __future__ import annotations

from typing import Any

from .context_processors import DEFAULT_CONTEXT_PROCESSORS, ContextProcessor, ContextSeed
from .role_contracts import get_role_contract


def _clean_text(value: Any, *, max_chars: int = 320) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(max_chars))]


def _build_preview(sections: dict[str, dict[str, Any]]) -> str:
    request = sections.get("request") if isinstance(sections.get("request"), dict) else {}
    contract = sections.get("contract") if isinstance(sections.get("contract"), dict) else {}
    slots = sections.get("slots") if isinstance(sections.get("slots"), dict) else {}
    unresolved = slots.get("unresolved") if isinstance(slots.get("unresolved"), list) else []
    unresolved_count = len(unresolved)
    message = _clean_text(request.get("message"), max_chars=160)
    objective = _clean_text(contract.get("objective"), max_chars=160)
    parts: list[str] = []
    if objective:
        parts.append(f"Objective: {objective}")
    elif message:
        parts.append(f"Request: {message}")
    if unresolved_count > 0:
        parts.append(f"Unresolved slots: {unresolved_count}")
    required_actions = (
        contract.get("required_actions")
        if isinstance(contract.get("required_actions"), list)
        else []
    )
    if required_actions:
        joined = ", ".join(str(item).strip() for item in required_actions[:4] if str(item).strip())
        if joined:
            parts.append(f"Required actions: {joined}")
    preview = " | ".join(parts).strip()
    return preview[:480]


def compile_working_context(
    *,
    seed: ContextSeed,
    processors: tuple[ContextProcessor, ...] | None = None,
) -> dict[str, Any]:
    selected_processors = processors if isinstance(processors, tuple) else DEFAULT_CONTEXT_PROCESSORS
    sections: dict[str, dict[str, Any]] = {}
    for processor in selected_processors:
        key, payload = processor(seed)
        clean_key = _clean_text(key, max_chars=64).lower()
        if not clean_key:
            continue
        if not isinstance(payload, dict):
            continue
        sections[clean_key] = payload
    return {
        "version": "working_context_v1",
        "sections": sections,
        "preview": _build_preview(sections),
    }


def scoped_working_context_for_role(
    *,
    working_context: dict[str, Any],
    role: str,
) -> dict[str, Any]:
    sections_raw = working_context.get("sections")
    sections = sections_raw if isinstance(sections_raw, dict) else {}
    contract = get_role_contract(role)
    allowed_tool_prefixes = [
        str(item).strip().lower()
        for item in contract.allowed_tool_prefixes
        if str(item).strip()
    ]
    scoped_sections: dict[str, Any] = {
        "request": sections.get("request", {}),
        "contract": sections.get("contract", {}),
        "slots": sections.get("slots", {}),
        "history": sections.get("history", {}),
        "memory": sections.get("memory", {}),
    }
    artifacts = sections.get("artifacts")
    if isinstance(artifacts, dict):
        scoped_artifacts = dict(artifacts)
    else:
        scoped_artifacts = {}
    scoped_artifacts["allowed_tool_prefixes"] = allowed_tool_prefixes
    scoped_artifacts["role"] = contract.role
    scoped_sections["artifacts"] = scoped_artifacts
    return {
        "version": str(working_context.get("version") or "working_context_v1"),
        "role": contract.role,
        "role_summary": contract.summary,
        "verification_obligations": list(contract.verification_obligations),
        "sections": scoped_sections,
        "preview": _build_preview(scoped_sections),
    }
