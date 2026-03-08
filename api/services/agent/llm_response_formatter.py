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
    keep_diagnostics: bool,
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
    ops_noise_rule = (
        "- Do not include operational status sections (delivery, contract gate, execution logs, verification logs).\n"
        if not keep_diagnostics
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
        "- Follow a NotebookLM-like flow: short answer first, evidence-backed points next, concise sources last.\n"
        "- Keep tone calm and low-noise; avoid verbose operational narration.\n"
        "- Do not default to reusable report skeletons unless explicitly requested by the user.\n"
        "- Remove process noise and internal execution narration unless explicitly asked.\n"
        f"{ops_noise_rule}"
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
_CITATION_ANCHOR_OPEN_RE = re.compile(
    r"<a\b[^>]*class=['\"][^'\"]*\bcitation\b[^'\"]*['\"][^>]*>",
    flags=re.IGNORECASE,
)
_ATTR_RE = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(['\"])(.*?)\2")
_EVIDENCE_SUFFIX_BLOCK_RE = re.compile(
    r"\n\nEvidence:\s+internal execution trace[\s\S]*\Z",
    flags=re.IGNORECASE,
)
_TOP_LEVEL_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.IGNORECASE | re.MULTILINE)
_DEDUPE_SECTION_TITLES = {"evidence citations", "recommended next steps"}
_NOISY_SECTION_TITLES = {
    "delivery status",
    "delivery attempt overview",
    "contract gate",
    "contract gate summary",
    "verification",
    "verification and quality assessment",
    "research execution status",
    "execution summary",
    "execution issues",
    "task understanding",
    "execution plan",
    "files and documents",
}
_NOISY_SECTION_SUBSTRINGS = (
    "delivery status",
    "delivery attempt",
    "contract gate",
    "verification and quality",
    "execution summary",
    "execution issues",
    "files and documents",
)


def _parse_ref_number_from_attrs(attrs: dict[str, str]) -> int:
    candidates = [
        attrs.get("data-evidence-id", ""),
        attrs.get("href", ""),
        attrs.get("id", ""),
        attrs.get("data-citation-number", ""),
    ]
    for candidate in candidates:
        match = re.search(r"(\d{1,4})", str(candidate or ""))
        if not match:
            continue
        try:
            value = int(match.group(1))
        except Exception:
            continue
        if value > 0:
            return value
    return 0


def _normalize_citation_anchor_attrs(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw

    def _replace(match: re.Match[str]) -> str:
        open_tag = match.group(0)
        attrs: dict[str, str] = {}
        for attr_match in _ATTR_RE.finditer(open_tag):
            key = str(attr_match.group(1) or "").strip().lower()
            value = str(attr_match.group(3) or "").strip()
            if key and key not in attrs:
                attrs[key] = value

        ref_id = _parse_ref_number_from_attrs(attrs)
        if ref_id <= 0:
            return open_tag

        normalized = [
            f"href='#evidence-{ref_id}'",
            f"id='citation-{ref_id}'",
            "class='citation'",
            f"data-evidence-id='evidence-{ref_id}'",
        ]
        citation_number = " ".join(str(attrs.get("data-citation-number") or "").split()).strip()
        if citation_number.isdigit():
            normalized.append(f"data-citation-number='{citation_number}'")

        for key in ("data-file-id", "data-source-url", "data-page", "data-strength", "data-strength-tier"):
            value = " ".join(str(attrs.get(key) or "").split()).strip()
            if value:
                safe = value.replace("'", "&#39;")
                normalized.append(f"{key}='{safe}'")

        return f"<a {' '.join(normalized)}>"

    return _CITATION_ANCHOR_OPEN_RE.sub(_replace, raw)


def _strip_redundant_evidence_suffix(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    has_citations = bool(
        re.search(r"(^|\n)##\s+Evidence\s+Citations\b", raw, flags=re.IGNORECASE)
        or re.search(r"\[\d{1,3}\]", raw)
    )
    if not has_citations:
        return raw
    return _EVIDENCE_SUFFIX_BLOCK_RE.sub("", raw).strip()


def _dedupe_terminal_sections(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return raw
    matches = list(_TOP_LEVEL_SECTION_RE.finditer(raw))
    if not matches:
        return raw

    kept_chunks: list[str] = []
    cursor = 0
    seen: set[str] = set()
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        kept_chunks.append(raw[cursor:section_start])
        title_key = " ".join(str(match.group(1) or "").lower().split()).strip()
        if title_key in _DEDUPE_SECTION_TITLES:
            if title_key in seen:
                cursor = section_end
                continue
            seen.add(title_key)
        kept_chunks.append(raw[section_start:section_end])
        cursor = section_end
    kept_chunks.append(raw[cursor:])
    normalized = "".join(kept_chunks)
    normalized = re.sub(r"\n{4,}", "\n\n\n", normalized)
    return normalized.strip()


def _section_title_key(value: str) -> str:
    return " ".join(str(value or "").lower().split()).strip()


def _strip_noise_sections(text: str, *, keep_diagnostics: bool) -> str:
    raw = str(text or "")
    if not raw or keep_diagnostics:
        return raw
    matches = list(_TOP_LEVEL_SECTION_RE.finditer(raw))
    if not matches:
        return raw

    kept_chunks: list[str] = []
    cursor = 0
    for idx, match in enumerate(matches):
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        kept_chunks.append(raw[cursor:section_start])
        title_key = _section_title_key(match.group(1))
        should_strip = (
            title_key in _NOISY_SECTION_TITLES
            or any(token in title_key for token in _NOISY_SECTION_SUBSTRINGS)
        )
        if not should_strip:
            kept_chunks.append(raw[section_start:section_end])
        cursor = section_end
    kept_chunks.append(raw[cursor:])
    normalized = "".join(kept_chunks)
    return re.sub(r"\n{4,}", "\n\n\n", normalized).strip()


def _diagnostics_requested(request_message: str) -> bool:
    message = " ".join(str(request_message or "").split()).strip().lower()
    if not message:
        return False
    return bool(
        re.search(
            r"\b(debug|diagnostic|log|trace|contract gate|delivery status|execution plan|internal)\b",
            message,
        )
    )


def _target_character_range(
    *,
    deep_research_mode: bool,
    verification_report: dict[str, Any],
    analytical_report: bool = False,
) -> tuple[int, int]:
    evidence_units = verification_report.get("evidence_units")
    evidence_count = len(evidence_units) if isinstance(evidence_units, list) else 0
    if deep_research_mode:
        if analytical_report:
            # Deep / expert mode → full-length structured report
            if evidence_count >= 12:
                return 8000, 20000
            if evidence_count >= 6:
                return 6000, 16000
            return 4000, 12000
        if evidence_count >= 12:
            return 3600, 8200
        if evidence_count >= 6:
            return 3000, 7200
        return 2200, 6200
    return 900, 2800


# ── Analytical report detection ───────────────────────────────────────────────
# Detects any question calling for a structured, multi-section analytical report
# across any domain — not limited to country, company, or industry questions.

_ANALYTICAL_INTENT_RE = re.compile(
    r"\b("
    r"analyz[ei]|analysis|analyse|"
    r"research\s+(?:on|about|into)|"
    r"report\s+on|"
    r"overview\s+of|"
    r"study\s+(?:of|on)|"
    r"profile\s+of|"
    r"assess(?:ment)?\s+(?:of|on)|"
    r"review\s+(?:of|on)|"
    r"investigate|investigation\s+(?:of|into)|"
    r"deep\s+(?:dive|research|analysis)|"
    r"comprehensive\s+(?:guide|overview|analysis|report|summary)|"
    r"(?:tell|explain)\s+me\s+(?:everything|all)\s+about|"
    r"background\s+(?:on|about)|"
    r"compare\s+(?:and\s+contrast\s+)?(?:[a-z]+\s+){0,4}(?:and|vs?\.?|versus)|"
    r"comparison\s+(?:of|between)|"
    r"evaluat(?:e|ion)\s+(?:of|on)|"
    r"brief(?:ing)?\s+on|"
    r"landscape\s+(?:of|for|in)|"
    r"state\s+of\s+(?:the\s+)?(?:art\s+)?(?:in\s+)?"
    r")\b",
    re.IGNORECASE,
)


def _is_analytical_report_question(request_message: str, *, deep_research_mode: bool = False) -> bool:
    """Return True when the question calls for a multi-section structured report.

    Triggers for ANY domain (science, law, tech, medicine, policy, sports, etc.)
    whenever analytical signals are present, or whenever deep research mode is
    active (the user asked for deep research, so structured output is expected).
    """
    text = str(request_message or "").strip()
    if not text:
        return False
    if deep_research_mode:
        # Deep / expert research always deserves a structured multi-section report.
        return True
    return bool(_ANALYTICAL_INTENT_RE.search(text))


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
    deep_research_mode = research_depth_tier in {"deep_research", "deep_analytics", "expert"}
    analytical_report = _is_analytical_report_question(request_text, deep_research_mode=deep_research_mode)
    target_min_chars, target_max_chars = _target_character_range(
        deep_research_mode=deep_research_mode,
        verification_report=verification_payload if isinstance(verification_payload, dict) else {},
        analytical_report=analytical_report,
    )
    child_friendly_mode = _requires_child_friendly_mode(
        request_message=str(request_message or ""),
        preferences=preferences_payload if isinstance(preferences_payload, dict) else {},
    )
    keep_diagnostics = _diagnostics_requested(request_message)
    blueprint = _plan_response_blueprint(
        request_message=str(request_message or "").strip(),
        requested_language=requested_language,
        answer_text=raw_answer,
        verification_report=verification_payload if isinstance(verification_payload, dict) else {},
        preferences=preferences_payload if isinstance(preferences_payload, dict) else {},
        child_friendly_mode=child_friendly_mode,
        keep_diagnostics=keep_diagnostics,
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
    analytical_report_rule = ""
    if analytical_report and deep_research_mode:
        analytical_report_rule = (
            "- STRUCTURED REPORT MODE: produce a full structured analytical report.\n"
            "- Open with an 'Executive Summary' (## H2 heading) — 2-4 concise paragraphs capturing the most important findings.\n"
            "- Follow with thematic sections (## H2 headings) chosen specifically for THIS topic and domain. "
            "Do NOT use generic or recycled section titles — pick the dimensions that matter most for the subject at hand. "
            "Examples: for a country → Geography, Demographics, Economy, Governance, Security, Infrastructure; "
            "for a technology → Architecture, Capabilities, Limitations, Use Cases, Market Adoption, Future Directions; "
            "for a medical topic → Epidemiology, Pathophysiology, Diagnosis, Treatment, Outcomes, Research Gaps; "
            "for a legal/policy question → Legal Framework, Key Provisions, Enforcement, Case Law, Comparative Analysis; "
            "for a company → Company Overview, Financials, Products & Market, Competitive Landscape, Leadership, Risk Factors. "
            "Always derive sections from the evidence — never force-fit irrelevant categories.\n"
            "- When numeric or time-series data is available, surface it in a markdown table (e.g. 'Key Metrics', 'Core Indicators', 'Performance Summary').\n"
            "- Include a 'Data Gaps & Uncertainties' section listing indicators that were sought but not found or are unreliable.\n"
            "- Include a brief chronological timeline when significant events add context.\n"
            "- Cite sources inline using citation markers; do not invent new claims.\n"
            "- Use clean H2/H3 hierarchy; avoid burying key stats in long prose — surface them in tables or bullets.\n"
        )
    deep_mode_rule = (
        "- Deep research mode: keep the response comprehensive with 6-10 substantive sections.\n"
        "- Deep research mode: preserve source richness and keep citation density high.\n"
        "- Deep research mode: do not collapse the answer into a short summary.\n"
        f"- Deep research mode: target approximately {target_min_chars}-{target_max_chars} characters excluding citation appendix.\n"
        if deep_research_mode
        else ""
    )
    diagnostics_rule = (
        ""
        if keep_diagnostics
        else "- Do not include operational sections such as Delivery Status, Contract Gate, execution logs, or verification diagnostics.\n"
    )
    template_rule = (
        ""
        if analytical_report
        else "- Avoid fixed or repeated canned section templates and reusable report skeletons.\n"
    )
    prompt = (
        "Rewrite the final agent response markdown using the provided adaptive blueprint.\n"
        "Rules:\n"
        "- Preserve all facts and statuses exactly.\n"
        "- Keep the response detailed and evidence-oriented.\n"
        "- Put the delivered outcome first.\n"
        "- Start with one short executive summary paragraph before deeper sections.\n"
        "- Follow a NotebookLM-style flow: concise answer first, evidence-backed points second, short source list last.\n"
        "- Adapt section structure and ordering to the request and blueprint.\n"
        "- Use concise professional language and clean markdown with low-noise, premium readability.\n"
        "- Keep section headings specific, calm, and high-signal.\n"
        "- Avoid raw HTML in body content; use markdown except citation anchors.\n"
        f"{template_rule}"
        "- Remove process noise and internal orchestration commentary unless user explicitly asked for it.\n"
        f"{diagnostics_rule}"
        "- If intent is unclear, ask a focused clarifying question instead of speculative summaries.\n"
        f"{simple_mode_rule}"
        f"{deep_mode_rule}"
        f"{analytical_report_rule}"
        "- Do not add new claims.\n"
        "- Keep evidence citations intact; include citation markers and citation section when available.\n"
        f"- {language_rule}\n"
        "- Return markdown text only.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    # Deep / expert research always gets full structured-report token budget.
    response_max_tokens = 2600
    if deep_research_mode:
        response_max_tokens = 8000  # analytical_report is always True for deep/expert
    polished = call_text_response(
        system_prompt=(
            "You are Maia's response writer. Produce adaptive, detailed, professional answers "
            f"{language_rule} "
            "without changing factual content."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=40,
        max_tokens=response_max_tokens,
    )
    cleaned = str(polished or "").strip()
    if not cleaned:
        return raw_answer
    if deep_research_mode:
        minimum_length = max(target_min_chars, int(len(raw_answer) * 0.6))
        if len(cleaned) < minimum_length:
            cleaned = raw_answer
    if len(cleaned) > int(target_max_chars * 1.35):
        cleaned = raw_answer
    citation_tail = _extract_citation_tail(raw_answer)
    if citation_tail and not _contains_citation_markers(cleaned):
        cleaned = f"{cleaned}\n\n{citation_tail}".strip()
    cleaned = _strip_wrapping_markdown_fence(cleaned)
    cleaned = _normalize_citation_anchor_attrs(cleaned)
    cleaned = _dedupe_terminal_sections(cleaned)
    cleaned = _strip_noise_sections(cleaned, keep_diagnostics=keep_diagnostics)
    cleaned = _strip_redundant_evidence_suffix(cleaned)
    cleaned = _redact_emails(cleaned, emails=request_emails)
    if _is_language_mismatch(
        request_message=request_message,
        requested_language=requested_language,
        candidate_text=cleaned,
    ):
        return raw_answer
    return cleaned or raw_answer
