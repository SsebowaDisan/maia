from __future__ import annotations

from typing import Any, Callable

ContextSeed = dict[str, Any]
ContextProcessor = Callable[[ContextSeed], tuple[str, dict[str, Any]]]


def _clean_text(value: Any, *, max_chars: int = 420) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(max_chars))]


def _clean_list(
    values: Any,
    *,
    limit: int = 8,
    max_item_chars: int = 220,
) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values:
        text = _clean_text(item, max_chars=max_item_chars)
        if not text or text in output:
            continue
        output.append(text)
        if len(output) >= max(1, int(limit)):
            break
    return output


def request_context_processor(seed: ContextSeed) -> tuple[str, dict[str, Any]]:
    return (
        "request",
        {
            "message": _clean_text(seed.get("message"), max_chars=520),
            "agent_goal": _clean_text(seed.get("agent_goal"), max_chars=360),
            "rewritten_task": _clean_text(seed.get("rewritten_task"), max_chars=900),
            "intent_tags": _clean_list(seed.get("intent_tags"), limit=12, max_item_chars=64),
        },
    )


def contract_context_processor(seed: ContextSeed) -> tuple[str, dict[str, Any]]:
    task_contract = seed.get("task_contract")
    contract = task_contract if isinstance(task_contract, dict) else {}
    return (
        "contract",
        {
            "objective": _clean_text(
                contract.get("objective") or seed.get("contract_objective"),
                max_chars=360,
            ),
            "required_outputs": _clean_list(
                contract.get("required_outputs") or seed.get("contract_outputs"),
                limit=8,
            ),
            "required_facts": _clean_list(
                contract.get("required_facts") or seed.get("contract_facts"),
                limit=8,
            ),
            "required_actions": _clean_list(
                contract.get("required_actions") or seed.get("contract_actions"),
                limit=8,
            ),
            "delivery_target": _clean_text(
                contract.get("delivery_target") or seed.get("contract_target"),
                max_chars=280,
            ),
            "success_checks": _clean_list(
                contract.get("success_checks") or seed.get("contract_success_checks"),
                limit=10,
                max_item_chars=240,
            ),
        },
    )


def slot_context_processor(seed: ContextSeed) -> tuple[str, dict[str, Any]]:
    rows = seed.get("contract_missing_slots")
    slots = rows if isinstance(rows, list) else []
    unresolved: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for row in slots[:16]:
        if not isinstance(row, dict):
            continue
        slot_payload = {
            "requirement": _clean_text(row.get("requirement"), max_chars=220),
            "description": _clean_text(row.get("description"), max_chars=260),
            "discoverable": bool(row.get("discoverable")),
            "blocking": bool(row.get("blocking")),
            "state": _clean_text(row.get("state"), max_chars=48).lower() or "open",
            "resolved_value": _clean_text(row.get("resolved_value"), max_chars=280),
        }
        if slot_payload["resolved_value"]:
            resolved.append(slot_payload)
        else:
            unresolved.append(slot_payload)
    return (
        "slots",
        {
            "unresolved": unresolved[:8],
            "resolved": resolved[:8],
        },
    )


def history_context_processor(seed: ContextSeed) -> tuple[str, dict[str, Any]]:
    return (
        "history",
        {
            "conversation_summary": _clean_text(seed.get("conversation_summary"), max_chars=520),
            "conversation_snippets": _clean_list(
                seed.get("conversation_snippets"),
                limit=8,
                max_item_chars=220,
            ),
        },
    )


def artifact_context_processor(seed: ContextSeed) -> tuple[str, dict[str, Any]]:
    return (
        "artifacts",
        {
            "selected_index_id": _clean_text(seed.get("selected_index_id"), max_chars=24),
            "selected_file_ids": _clean_list(
                seed.get("selected_file_ids"),
                limit=20,
                max_item_chars=120,
            ),
            "planned_search_terms": _clean_list(
                seed.get("planned_search_terms"),
                limit=12,
                max_item_chars=120,
            ),
            "planned_keywords": _clean_list(
                seed.get("planned_keywords"),
                limit=20,
                max_item_chars=80,
            ),
        },
    )


def memory_context_processor(seed: ContextSeed) -> tuple[str, dict[str, Any]]:
    return (
        "memory",
        {
            "session_context_snippets": _clean_list(
                seed.get("session_context_snippets"),
                limit=6,
                max_item_chars=240,
            ),
            "long_term_memory_snippets": _clean_list(
                seed.get("memory_context_snippets"),
                limit=6,
                max_item_chars=240,
            ),
        },
    )


DEFAULT_CONTEXT_PROCESSORS: tuple[ContextProcessor, ...] = (
    request_context_processor,
    contract_context_processor,
    slot_context_processor,
    history_context_processor,
    artifact_context_processor,
    memory_context_processor,
)

