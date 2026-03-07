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
from api.services.chat.language import (
    build_response_language_rule,
    infer_user_language_code,
    resolve_response_language,
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
    requested_language: str | None,
    answer_text: str,
    verification_report: dict[str, Any],
    preferences: dict[str, Any],
    child_friendly_mode: bool,
) -> dict[str, Any]:
    language_rule = build_response_language_rule(
        requested_language=requested_language,
        latest_message=request_message,
    )
    simple_section_rule = (
        "- Include one section titled 'Simple Explanation (For a 5-Year-Old)' with plain words and short examples.\n"
        if child_friendly_mode
        else ""
    )
    plan_prompt = (
        "Design a response blueprint for a final agent answer.\n"
        "Return one JSON object only with keys:\n"
        '{ "response_style": "string", "detail_level": "high", "tone": "string", "sections": [{"title":"string","purpose":"string","format":"paragraphs|bullets|table|mixed"}] }\n'
        "Rules:\n"
        "- Section titles must be specific to this request, not generic reusable template labels.\n"
        "- Keep response detail_level as high.\n"
        "- Use 2-8 sections.\n"
        "- Put direct task outcome first, then supporting details and citations.\n"
        "- Do not default to reusable report skeletons unless explicitly requested by the user.\n"
        "- Remove process noise and internal execution narration unless explicitly asked.\n"
        "- If intent is unclear/noisy, produce a clarifying-question structure instead of assumptions.\n"
        "- Preserve evidence and compliance visibility.\n"
        f"{simple_section_rule}"
        f"- {language_rule}\n"
        "- Do not invent facts.\n\n"
        f"User request:\n{request_message}\n\n"
        f"Current answer draft:\n{answer_text[:6000]}\n\n"
        f"Verification report:\n{json.dumps(sanitize_json_value(verification_report), ensure_ascii=True)}\n\n"
        f"Preferences:\n{json.dumps(sanitize_json_value(preferences), ensure_ascii=True)}"
    )
    blueprint = call_json_response(
        system_prompt=(
            "You are an expert technical editor for enterprise AI agents. "
            f"{language_rule} "
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


_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_URL_RE = re.compile(r"https?://\S+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", flags=re.IGNORECASE)


def _normalize_for_language_detection(text: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    cleaned = _FENCED_BLOCK_RE.sub(" ", raw)
    cleaned = _INLINE_CODE_RE.sub(" ", cleaned)
    cleaned = _MARKDOWN_LINK_RE.sub(lambda match: f" {match.group(1)} ", cleaned)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:2400]


def _is_language_mismatch(
    *,
    request_message: str,
    requested_language: str | None,
    candidate_text: str,
) -> bool:
    request_clean = _normalize_for_language_detection(request_message)
    candidate_clean = _normalize_for_language_detection(candidate_text)
    if len(candidate_clean) < 80:
        return False
    expected = resolve_response_language(requested_language, request_clean)
    observed = infer_user_language_code(candidate_clean)
    if not expected or not observed:
        return False
    if expected == observed:
        return False
    # Treat English requests as strict to avoid accidental Portuguese/Spanish rewrites.
    if expected == "en":
        return True
    # For non-English requests, still guard against clear language flips.
    return True


def _strip_wrapping_markdown_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    lines = cleaned.splitlines()
    while (
        len(lines) >= 3
        and lines[0].strip().startswith("```")
        and lines[-1].strip() == "```"
    ):
        lines = lines[1:-1]
    return "\n".join(lines).strip()


def _emails_from_text(*parts: str) -> set[str]:
    emails: set[str] = set()
    for part in parts:
        for match in _EMAIL_RE.findall(str(part or "")):
            normalized = match.strip().lower()
            if normalized:
                emails.add(normalized)
    return emails


def _redact_emails(text: str, *, emails: set[str]) -> str:
    result = str(text or "")
    if not result or not emails:
        return result
    for email in sorted(emails, key=len, reverse=True):
        result = re.sub(re.escape(email), "the recipient", result, flags=re.IGNORECASE)
    return result


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def _requires_child_friendly_mode(
    *,
    request_message: str,
    preferences: dict[str, Any] | None,
) -> bool:
    prefs = preferences if isinstance(preferences, dict) else {}
    explicit = _coerce_bool(prefs.get("simple_explanation_required"))
    if explicit is not None:
        return explicit
    if not env_bool("MAIA_AGENT_LLM_RESPONSE_AUDIENCE_DETECT_ENABLED", default=True):
        return False
    payload = call_json_response(
        system_prompt=(
            "You classify whether a response should include child-friendly simplification. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "simple_explanation_required": true }\n'
            "Rules:\n"
            "- Infer from request and preferences.\n"
            "- Return false when not explicitly needed.\n\n"
            f"Input:\n{json.dumps(sanitize_json_value({'request_message': request_message, 'preferences': prefs}), ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=80,
    )
    llm_flag = _coerce_bool(payload.get("simple_explanation_required") if isinstance(payload, dict) else None)
    return bool(llm_flag)


def polish_final_response(
    *,
    request_message: str,
    requested_language: str | None = None,
    answer_text: str,
    verification_report: dict[str, Any] | None = None,
    preferences: dict[str, Any] | None = None,
) -> str:
    request_text = str(request_message or "").strip()
    request_emails = _emails_from_text(request_text)
    raw_answer = _redact_emails(
        _strip_wrapping_markdown_fence(str(answer_text or "").strip()),
        emails=request_emails,
    )
    if not raw_answer:
        return answer_text
    if not env_bool("MAIA_AGENT_LLM_RESPONSE_POLISH_ENABLED", default=True):
        return raw_answer
    language_rule = build_response_language_rule(
        requested_language=requested_language,
        latest_message=request_message,
    )

    verification_payload = sanitize_json_value(verification_report or {})
    preferences_payload = sanitize_json_value(preferences or {})
    research_depth_tier = (
        " ".join(str((preferences_payload or {}).get("research_depth_tier") or "").split())
        .strip()
        .lower()
    )
    deep_research_mode = research_depth_tier in {"deep_research", "deep_analytics"}
    child_friendly_mode = _requires_child_friendly_mode(
        request_message=str(request_message or ""),
        preferences=preferences_payload if isinstance(preferences_payload, dict) else {},
    )
    blueprint = _plan_response_blueprint(
        request_message=str(request_message or "").strip(),
        requested_language=requested_language,
        answer_text=raw_answer,
        verification_report=verification_payload if isinstance(verification_payload, dict) else {},
        preferences=preferences_payload if isinstance(preferences_payload, dict) else {},
        child_friendly_mode=child_friendly_mode,
    )
    payload = {
        "request_message": str(request_message or "").strip(),
        "answer_text": raw_answer,
        "response_blueprint": blueprint,
        "verification_report": verification_payload,
        "preferences": preferences_payload,
    }
    simple_mode_rule = (
        "- Include a short 'Simple Explanation (For a 5-Year-Old)' section in plain words.\n"
        if child_friendly_mode
        else ""
    )
    deep_mode_rule = (
        "- Deep research mode: keep the response comprehensive with multiple substantive sections.\n"
        "- Deep research mode: preserve source richness and keep citation density high.\n"
        "- Deep research mode: do not collapse the answer into a short summary.\n"
        if deep_research_mode
        else ""
    )
    prompt = (
        "Rewrite the final agent response markdown using the provided adaptive blueprint.\n"
        "Rules:\n"
        "- Preserve all facts and statuses exactly.\n"
        "- Keep the response detailed and evidence-oriented.\n"
        "- Put the delivered outcome first.\n"
        "- Adapt section structure and ordering to the request and blueprint.\n"
        "- Use concise professional language and clean markdown.\n"
        "- Avoid fixed or repeated canned section templates and reusable report skeletons.\n"
        "- Remove process noise and internal orchestration commentary unless user explicitly asked for it.\n"
        "- If intent is unclear, ask a focused clarifying question instead of speculative summaries.\n"
        f"{simple_mode_rule}"
        f"{deep_mode_rule}"
        "- Do not add new claims.\n"
        "- Keep evidence citations intact; include citation markers and citation section when available.\n"
        f"- {language_rule}\n"
        "- Return markdown text only.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    polished = call_text_response(
        system_prompt=(
            "You are Maia's response writer. Produce adaptive, detailed, professional answers "
            f"{language_rule} "
            "without changing factual content."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=18,
        max_tokens=2600,
    )
    cleaned = str(polished or "").strip()
    if not cleaned:
        return raw_answer
    if deep_research_mode:
        minimum_length = max(900, int(len(raw_answer) * 0.6))
        if len(cleaned) < minimum_length:
            cleaned = raw_answer
    citation_tail = _extract_citation_tail(raw_answer)
    if citation_tail and not _contains_citation_markers(cleaned):
        cleaned = f"{cleaned}\n\n{citation_tail}".strip()
    cleaned = _strip_wrapping_markdown_fence(cleaned)
    cleaned = _redact_emails(cleaned, emails=request_emails)
    if _is_language_mismatch(
        request_message=request_message,
        requested_language=requested_language,
        candidate_text=cleaned,
    ):
        return raw_answer
    return cleaned or raw_answer
