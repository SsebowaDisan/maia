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


def _normalize_blueprint(payload: dict[str, Any] | None) -> dict[str, Any]:
    fallback = {
        "response_style": "adaptive_detailed",
        "detail_level": "high",
        "tone": "professional",
        "sections": [
            {
                "title": "Answer",
                "purpose": "Respond directly with concrete evidence-backed detail.",
                "format": "mixed",
            },
        ],
    }
    if not isinstance(payload, dict):
        return fallback

    response_style = (
        " ".join(str(payload.get("response_style") or "").split()).strip()[:80]
        or fallback["response_style"]
    )
    detail_level = (
        " ".join(str(payload.get("detail_level") or "").split()).strip()[:40]
        or fallback["detail_level"]
    )
    tone = " ".join(str(payload.get("tone") or "").split()).strip()[:40] or fallback["tone"]

    sections: list[dict[str, str]] = []
    raw_sections = payload.get("sections")
    if isinstance(raw_sections, list):
        for row in raw_sections[:8]:
            if not isinstance(row, dict):
                continue
            title = " ".join(str(row.get("title") or "").split()).strip()[:120]
            purpose = " ".join(str(row.get("purpose") or "").split()).strip()[:260]
            fmt = " ".join(str(row.get("format") or "").split()).strip()[:40]
            if not title and not purpose:
                continue
            sections.append(
                {
                    "title": title or "Section",
                    "purpose": purpose or "Provide detailed, evidence-grounded information.",
                    "format": fmt or "paragraphs",
                }
            )
    if not sections:
        sections = fallback["sections"]

    return {
        "response_style": response_style,
        "detail_level": detail_level,
        "tone": tone,
        "sections": sections,
    }


def _plan_response_blueprint(
    *,
    request_message: str,
    answer_text: str,
    verification_report: dict[str, Any],
    preferences: dict[str, Any],
) -> dict[str, Any]:
    plan_prompt = (
        "Design a response blueprint for a final agent answer.\n"
        "Return one JSON object only with keys:\n"
        '{ "response_style": "string", "detail_level": "high", "tone": "string", "sections": [{"title":"string","purpose":"string","format":"paragraphs|bullets|table|mixed"}] }\n'
        "Rules:\n"
        "- Section titles must be specific to this request, not generic reusable template labels.\n"
        "- Keep response detail_level as high.\n"
        "- Use 2-8 sections.\n"
        "- Do not default to reusable report skeletons unless explicitly requested by the user.\n"
        "- If intent is unclear/noisy, produce a clarifying-question structure instead of assumptions.\n"
        "- Preserve evidence and compliance visibility.\n"
        "- Do not invent facts.\n\n"
        f"User request:\n{request_message}\n\n"
        f"Current answer draft:\n{answer_text[:6000]}\n\n"
        f"Verification report:\n{json.dumps(sanitize_json_value(verification_report), ensure_ascii=True)}\n\n"
        f"Preferences:\n{json.dumps(sanitize_json_value(preferences), ensure_ascii=True)}"
    )
    blueprint = call_json_response(
        system_prompt=(
            "You are an expert technical editor for enterprise AI agents. "
            "You design adaptive markdown structures and return JSON only."
        ),
        user_prompt=plan_prompt,
        temperature=0.1,
        timeout_seconds=14,
        max_tokens=1200,
    )
    return _normalize_blueprint(blueprint)


def _extract_citation_tail(answer_text: str) -> str:
    text = str(answer_text or "")
    if not text.strip():
        return ""
    match = re.search(r"(^|\n)##\s+Evidence\s+Citations\b", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return text[match.start() :].strip()


def _contains_citation_markers(answer_text: str) -> bool:
    text = str(answer_text or "")
    if not text.strip():
        return False
    if re.search(r"(^|\n)##\s+Evidence\s+Citations\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\[\d{1,3}\]", text):
        return True
    return False


def polish_final_response(
    *,
    request_message: str,
    answer_text: str,
    verification_report: dict[str, Any] | None = None,
    preferences: dict[str, Any] | None = None,
) -> str:
    if not env_bool("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", default=True):
        return answer_text
    raw_answer = str(answer_text or "").strip()
    if not raw_answer:
        return answer_text

    verification_payload = sanitize_json_value(verification_report or {})
    preferences_payload = sanitize_json_value(preferences or {})
    blueprint = _plan_response_blueprint(
        request_message=str(request_message or "").strip(),
        answer_text=raw_answer,
        verification_report=verification_payload if isinstance(verification_payload, dict) else {},
        preferences=preferences_payload if isinstance(preferences_payload, dict) else {},
    )
    payload = {
        "request_message": str(request_message or "").strip(),
        "answer_text": raw_answer,
        "response_blueprint": blueprint,
        "verification_report": verification_payload,
        "preferences": preferences_payload,
    }
    prompt = (
        "Rewrite the final agent response markdown using the provided adaptive blueprint.\n"
        "Rules:\n"
        "- Preserve all facts and statuses exactly.\n"
        "- Keep the response detailed and evidence-oriented.\n"
        "- Adapt section structure and ordering to the request and blueprint.\n"
        "- Use concise professional language and clean markdown.\n"
        "- Avoid fixed or repeated canned section templates and reusable report skeletons.\n"
        "- If intent is unclear, ask a focused clarifying question instead of speculative summaries.\n"
        "- Do not add new claims.\n"
        "- Keep evidence citations intact; include citation markers and citation section when available.\n"
        "- Return markdown text only.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    polished = call_text_response(
        system_prompt=(
            "You are Maia's response writer. Produce adaptive, detailed, professional answers "
            "without changing factual content."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=18,
        max_tokens=2600,
    )
    cleaned = str(polished or "").strip()
    if not cleaned:
        return answer_text
    citation_tail = _extract_citation_tail(raw_answer)
    if citation_tail and not _contains_citation_markers(cleaned):
        cleaned = f"{cleaned}\n\n{citation_tail}".strip()
    return cleaned
