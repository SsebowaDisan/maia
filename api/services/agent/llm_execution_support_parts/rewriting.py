from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool

_SCOPE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")


def _tokenize_scope(text: str) -> set[str]:
    def _canonical(raw: str) -> str:
        token = str(raw or "").strip().lower()
        for suffix in ("ization", "ation", "ments", "ment", "ities", "ity", "ing", "ed", "s"):
            if token.endswith(suffix) and (len(token) - len(suffix)) >= 4:
                token = token[: -len(suffix)]
                break
        return token

    return {
        _canonical(match.group(0))
        for match in _SCOPE_WORD_RE.finditer(str(text or ""))
        if len(match.group(0)) >= 4
    }


def _rewrite_scope_drifted(*, source_text: str, rewritten_text: str) -> bool:
    source_tokens = _tokenize_scope(source_text)
    rewritten_tokens = _tokenize_scope(rewritten_text)
    if not rewritten_tokens:
        return True
    if not source_tokens:
        return False
    novel_tokens = rewritten_tokens.difference(source_tokens)
    if not novel_tokens:
        return False
    novel_ratio = len(novel_tokens) / max(1, len(rewritten_tokens))
    novel_limit = max(4, int(len(source_tokens) * 0.75))
    return len(novel_tokens) > novel_limit or novel_ratio >= 0.45


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
        "- Preserve the original scope; do not add arbitrary recency windows, academic-only framing, or source constraints unless the user explicitly asked for them.\n"
        "- For a general research request, frame the task as a balanced evidence-backed overview, not a latest-papers hunt.\n"
        "- If the user asks for an email/report deliverable, ensure the brief keeps citations and structured delivery in scope.\n"
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
    source_scope_text = " ".join([clean_message, clean_goal]).strip()
    if _rewrite_scope_drifted(source_text=source_scope_text, rewritten_text=detailed_task):
        detailed_task = source_scope_text[:900] if source_scope_text else clean_message[:900]

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
