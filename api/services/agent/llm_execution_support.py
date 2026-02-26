from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value


def suggest_failure_recovery(
    *,
    request_message: str,
    tool_id: str,
    step_title: str,
    error_text: str,
    recent_steps: list[dict[str, Any]],
) -> str:
    if not env_bool("MAIA_AGENT_LLM_RECOVERY_ENABLED", default=True):
        return ""
    payload = {
        "request_message": str(request_message or "").strip(),
        "tool_id": str(tool_id or "").strip(),
        "step_title": str(step_title or "").strip(),
        "error_text": str(error_text or "").strip(),
        "recent_steps": sanitize_json_value(recent_steps),
    }
    prompt = (
        "Given a failed tool execution, provide one concise recovery action.\n"
        "Return JSON only:\n"
        '{ "recovery_hint": "single actionable sentence" }\n'
        "Rules:\n"
        "- Be concrete and safe.\n"
        "- Do not suggest exposing secrets.\n"
        "- Max 140 characters.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You propose concise remediation actions for workflow failures. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return ""
    hint = " ".join(str(response.get("recovery_hint") or "").split()).strip()
    return hint[:140]


def polish_email_content(
    *,
    subject: str,
    body_text: str,
    recipient: str,
    context_summary: str = "",
) -> dict[str, str]:
    if not env_bool("MAIA_AGENT_LLM_EMAIL_POLISH_ENABLED", default=True):
        return {"subject": subject, "body_text": body_text}
    payload = {
        "recipient": str(recipient or "").strip(),
        "subject": str(subject or "").strip(),
        "body_text": str(body_text or "").strip(),
        "context_summary": str(context_summary or "").strip(),
    }
    prompt = (
        "Polish this email draft for clarity and executive tone.\n"
        "Return JSON only in this schema:\n"
        '{ "subject": "string", "body_text": "string" }\n'
        "Rules:\n"
        "- Preserve factual content; do not invent claims.\n"
        "- Keep tone professional and concise.\n"
        "- Keep body under 1400 characters.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You edit outbound business emails for clarity and professionalism. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=14,
        max_tokens=1100,
    )
    if not isinstance(response, dict):
        return {"subject": subject, "body_text": body_text}
    clean_subject = " ".join(str(response.get("subject") or "").split()).strip()[:180]
    clean_body = str(response.get("body_text") or "").strip()[:1400]
    if not clean_subject:
        clean_subject = str(subject or "").strip()
    if not clean_body:
        clean_body = str(body_text or "").strip()
    return {"subject": clean_subject, "body_text": clean_body}
