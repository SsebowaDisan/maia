from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import (
    call_json_response,
    call_text_response,
    env_bool,
    sanitize_json_value,
)


def _normalize_url_list(raw_urls: Any, *, limit: int = 5) -> list[str]:
    if not isinstance(raw_urls, list):
        return []
    urls: list[str] = []
    for item in raw_urls:
        value = str(item or "").strip()
        if not value:
            continue
        if not (value.startswith("http://") or value.startswith("https://")):
            continue
        if value in urls:
            continue
        urls.append(value)
        if len(urls) >= max(1, int(limit)):
            break
    return urls


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


def polish_contact_form_content(
    *,
    subject: str,
    message_text: str,
    website_url: str,
    context_summary: str = "",
) -> dict[str, str]:
    if not env_bool("MAIA_AGENT_LLM_CONTACT_POLISH_ENABLED", default=True):
        return {"subject": subject, "message_text": message_text}
    payload = {
        "website_url": str(website_url or "").strip(),
        "subject": str(subject or "").strip(),
        "message_text": str(message_text or "").strip(),
        "context_summary": str(context_summary or "").strip(),
    }
    prompt = (
        "Polish this website contact-form outreach content.\n"
        "Return JSON only in this schema:\n"
        '{ "subject": "string", "message_text": "string" }\n'
        "Rules:\n"
        "- Keep it concise, professional, and factual.\n"
        "- Do not invent claims or personal data.\n"
        "- Message must be under 900 characters.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You edit website contact-form outreach for enterprise communication. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=14,
        max_tokens=900,
    )
    if not isinstance(response, dict):
        return {"subject": subject, "message_text": message_text}
    clean_subject = " ".join(str(response.get("subject") or "").split()).strip()[:180]
    clean_message = str(response.get("message_text") or "").strip()[:900]
    if not clean_subject:
        clean_subject = str(subject or "").strip()
    if not clean_message:
        clean_message = str(message_text or "").strip()
    return {"subject": clean_subject, "message_text": clean_message}


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
            if _semantic_overlap(normalized_step, normalized_phrase) >= 0.62:
                return True
        return False

    heuristic_filtered = [step for step in normalized_candidates if not _is_task_restatement(step)]

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
    return [step for step in llm_steps if not _is_task_restatement(step)][: max(1, int(max_items))]


def rewrite_task_for_execution(
    *,
    message: str,
    agent_goal: str | None = None,
    conversation_summary: str = "",
) -> dict[str, Any]:
    """Rewrite user request into a detailed execution brief."""
    clean_message = " ".join(str(message or "").split()).strip()
    clean_goal = " ".join(str(agent_goal or "").split()).strip()
    clean_context = " ".join(str(conversation_summary or "").split()).strip()
    if not clean_message:
        return {"detailed_task": "", "deliverables": [], "constraints": []}
    if not env_bool("MAIA_AGENT_LLM_TASK_REWRITE_ENABLED", default=True):
        fallback_text = clean_message
        if clean_goal:
            fallback_text = f"{fallback_text}\nGoal: {clean_goal}"
        if clean_context:
            fallback_text = f"{fallback_text}\nContext: {clean_context}"
        return {
            "detailed_task": fallback_text[:1000],
            "deliverables": [],
            "constraints": [],
        }

    payload = {
        "message": clean_message,
        "agent_goal": clean_goal,
        "conversation_summary": clean_context,
    }
    prompt = (
        "Rewrite this user request into an execution-ready task brief.\n"
        "Return JSON only:\n"
        '{ "detailed_task": "string", "deliverables": ["..."], "constraints": ["..."] }\n'
        "Rules:\n"
        "- Preserve user intent exactly; do not invent facts.\n"
        "- Keep `detailed_task` concise but specific (max 900 chars).\n"
        "- Include 1-6 deliverables when implied.\n"
        "- Include only explicit constraints from request/context.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You convert user requests into precise enterprise execution briefs. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=420,
    )
    if not isinstance(response, dict):
        return {
            "detailed_task": clean_message[:1000],
            "deliverables": [],
            "constraints": [],
        }

    detailed_task = " ".join(str(response.get("detailed_task") or "").split()).strip()[:900]
    if not detailed_task:
        detailed_task = clean_message[:900]

    def _clean_list(raw: Any, *, limit: int) -> list[str]:
        if not isinstance(raw, list):
            return []
        items: list[str] = []
        for row in raw:
            text = " ".join(str(row or "").split()).strip()
            if not text or text in items:
                continue
            items.append(text[:220])
            if len(items) >= limit:
                break
        return items

    deliverables = _clean_list(response.get("deliverables"), limit=6)
    constraints = _clean_list(response.get("constraints"), limit=6)
    return {
        "detailed_task": detailed_task,
        "deliverables": deliverables,
        "constraints": constraints,
    }


def build_location_delivery_brief(
    *,
    request_message: str,
    objective: str,
    report_body: str,
    browser_findings: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a fact-grounded brief via LLM (no keyword heuristics)."""
    if not env_bool("MAIA_AGENT_LLM_LOCATION_BRIEF_ENABLED", default=True):
        return {"summary": "", "address": "", "evidence_urls": [], "confidence": "unknown"}
    payload = {
        "request_message": " ".join(str(request_message or "").split()).strip()[:480],
        "objective": " ".join(str(objective or "").split()).strip()[:480],
        "report_body": str(report_body or "").strip()[:1800],
        "browser_findings": sanitize_json_value(browser_findings or {}),
        "sources": sanitize_json_value(sources or []),
    }
    prompt = (
        "Synthesize a location answer from task evidence for an outbound email.\n"
        "Return JSON only:\n"
        '{ "summary": "string", "address": "string", "evidence_urls": ["..."], "confidence": "high|medium|low|unknown" }\n'
        "Rules:\n"
        "- Use only evidence from input payload.\n"
        "- `summary` must state where the company is found or state that evidence is insufficient.\n"
        "- `address` should be empty if not explicitly present in evidence.\n"
        "- Include up to 5 relevant evidence URLs.\n"
        "- Do not invent data.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You extract location findings from evidence for enterprise reporting. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=320,
    )
    if not isinstance(response, dict):
        return {"summary": "", "address": "", "evidence_urls": [], "confidence": "unknown"}

    summary = " ".join(str(response.get("summary") or "").split()).strip()[:420]
    address = " ".join(str(response.get("address") or "").split()).strip()[:260]
    confidence_raw = str(response.get("confidence") or "").strip().lower()
    confidence = confidence_raw if confidence_raw in {"high", "medium", "low", "unknown"} else "unknown"
    urls = _normalize_url_list(response.get("evidence_urls"), limit=5)

    if not urls and isinstance(sources, list):
        urls = _normalize_url_list([row.get("url") for row in sources if isinstance(row, dict)], limit=5)
    return {
        "summary": summary,
        "address": address,
        "evidence_urls": urls,
        "confidence": confidence,
    }

