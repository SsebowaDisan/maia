from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import (
    call_json_response,
    call_text_response,
    env_bool,
    sanitize_json_value,
)


def summarize_conversation_window(
    *,
    latest_user_message: str,
    turns: list[dict[str, str]],
) -> str:
    """Summarize recent conversation turns into a concise planning context."""
    cleaned_turns: list[dict[str, str]] = []
    for row in list(turns or [])[:8]:
        if not isinstance(row, dict):
            continue
        user = " ".join(str(row.get("user") or "").split()).strip()
        assistant = " ".join(str(row.get("assistant") or "").split()).strip()
        if not user and not assistant:
            continue
        cleaned_turns.append({"user": user[:240], "assistant": assistant[:280]})
    if not cleaned_turns:
        return ""
    if not env_bool("MAIA_AGENT_LLM_CONTEXT_SUMMARY_ENABLED", default=True):
        segments: list[str] = []
        for row in cleaned_turns[-4:]:
            user_part = str(row.get("user") or "").strip()
            assistant_part = str(row.get("assistant") or "").strip()
            if user_part:
                segments.append(f"User asked: {user_part}")
            if assistant_part:
                segments.append(f"Assistant answered: {assistant_part}")
        merged = " ".join(segments).strip()
        return merged[:500]

    payload = {
        "latest_user_message": " ".join(str(latest_user_message or "").split()).strip(),
        "recent_turns": cleaned_turns[-6:],
    }
    prompt = (
        "Summarize the recent conversation context for an execution planner.\n"
        "Return one concise paragraph only.\n"
        "Rules:\n"
        "- Focus on unresolved goals, requested outputs, and delivery targets.\n"
        "- Preserve facts only.\n"
        "- Max 480 characters.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    summary = call_text_response(
        system_prompt=(
            "You summarize conversation history for task execution context. "
            "Return concise plain text only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=180,
    )
    return " ".join(str(summary or "").split()).strip()[:480]


def summarize_step_outcome(
    *,
    request_message: str,
    tool_id: str,
    step_title: str,
    result_summary: str,
    result_data: dict[str, Any] | None = None,
) -> dict[str, str]:
    if not env_bool("MAIA_AGENT_LLM_STEP_SUMMARY_ENABLED", default=True):
        return {"summary": "", "suggestion": ""}
    payload = {
        "request_message": str(request_message or "").strip(),
        "tool_id": str(tool_id or "").strip(),
        "step_title": str(step_title or "").strip(),
        "result_summary": str(result_summary or "").strip(),
        "result_data": sanitize_json_value(result_data or {}),
    }
    prompt = (
        "Summarize this completed step and suggest one context-aware next move.\n"
        "Return JSON only:\n"
        '{ "summary": "short summary", "suggestion": "single next step" }\n'
        "Rules:\n"
        "- Keep summary under 140 characters.\n"
        "- Keep suggestion under 160 characters.\n"
        "- Be concrete and avoid generic advice.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You produce concise operational summaries for enterprise agent runs. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=11,
        max_tokens=220,
    )
    if not isinstance(response, dict):
        return {"summary": "", "suggestion": ""}
    summary = " ".join(str(response.get("summary") or "").split()).strip()[:140]
    suggestion = " ".join(str(response.get("suggestion") or "").split()).strip()[:160]
    return {"summary": summary, "suggestion": suggestion}
