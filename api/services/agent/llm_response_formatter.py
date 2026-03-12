from __future__ import annotations

import json
from typing import Any

from api.services.agent.llm_runtime import (
    call_json_response,
    call_text_response,
    env_bool,
    sanitize_json_value,
)
from api.services.agent.llm_response_formatter_text_ops import (
    coerce_bool,
    contains_citation_markers,
    dedupe_terminal_sections,
    diagnostics_requested,
    emails_from_text,
    extract_citation_tail,
    is_analytical_report_question,
    is_language_mismatch,
    normalize_citation_anchor_attrs,
    redact_emails,
    strip_noise_sections,
    strip_redundant_evidence_suffix,
    strip_wrapping_markdown_fence,
    target_character_range,
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
        "Design a deep, well-structured response blueprint for a final agent answer.\n"
        "Return one JSON object only with keys:\n"
        '{ "response_style": "string", "detail_level": "high", "tone": "string", "sections": [{"title":"string","purpose":"string","format":"paragraphs|bullets|table|mixed"}] }\n'
        "Rules:\n"
        "- Section titles must be specific to this request, not generic reusable template labels.\n"
        "- Keep response detail_level as high.\n"
        "- For research, analytical, or comparative questions: use 4-8 substantive sections covering distinct dimensions "
        "(e.g. key findings, background/context, mechanisms, data/evidence, trade-offs, implications, limitations, next steps).\n"
        "- For direct task outcomes (e.g. 'send email', 'find contact'): 2-4 sections, outcome first, then supporting evidence.\n"
        "- Each section purpose must specify what specific insight or evidence it will surface — not just 'provide details'.\n"
        "- Put direct task outcome first, then supporting details, analysis, and citations.\n"
        "- Keep tone precise and authoritative; write at senior-analyst depth for the target domain.\n"
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
            "You are an expert research editor for enterprise AI agents. "
            f"{language_rule} "
            "You design deep, analytically rich markdown structures for research-grade answers and return JSON only."
        ),
        user_prompt=plan_prompt,
        temperature=0.1,
        timeout_seconds=14,
        max_tokens=1200,
    )
    return _normalize_blueprint(blueprint)


def _requires_child_friendly_mode(
    *,
    request_message: str,
    preferences: dict[str, Any] | None,
) -> bool:
    prefs = preferences if isinstance(preferences, dict) else {}
    explicit = coerce_bool(prefs.get("simple_explanation_required"))
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
    llm_flag = coerce_bool(payload.get("simple_explanation_required") if isinstance(payload, dict) else None)
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
    request_emails = emails_from_text(request_text)
    fallback_answer = redact_emails(str(answer_text or ""), emails=request_emails)
    answer_source = strip_wrapping_markdown_fence(str(answer_text or ""))
    raw_answer = redact_emails(
        answer_source,
        emails=request_emails,
    )
    if not str(raw_answer).strip():
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
    analytical_report = is_analytical_report_question(
        request_text,
        deep_research_mode=deep_research_mode,
    )
    target_min_chars, target_max_chars = target_character_range(
        deep_research_mode=deep_research_mode,
        verification_report=verification_payload if isinstance(verification_payload, dict) else {},
        analytical_report=analytical_report,
    )
    child_friendly_mode = _requires_child_friendly_mode(
        request_message=str(request_message or ""),
        preferences=preferences_payload if isinstance(preferences_payload, dict) else {},
    )
    keep_diagnostics = diagnostics_requested(request_message)
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
            "- STRUCTURED REPORT MODE: produce a comprehensive analytical report — this is the primary deliverable.\n"
            "- Open with an 'Executive Summary' (## H2 heading) — 3-5 substantive paragraphs that capture the most important findings, key data points, and strategic implications. Not a short teaser — a real executive brief.\n"
            "- Follow with 6-10 thematic sections (## H2 headings) chosen specifically for THIS topic and domain. "
            "Do NOT use generic or recycled section titles — pick the dimensions that matter most for the subject at hand. "
            "Always derive sections from the evidence — never force-fit irrelevant categories.\n"
            "- Each section must be developed with 3-5 substantive paragraphs. Include specific data, expert context, mechanisms, and implications. Never leave a section at a one-paragraph surface summary.\n"
            "- When numeric or time-series data is available, surface it in a markdown table with source citations.\n"
            "- Include a 'Key Findings & Data Points' section that consolidates the most important quantitative evidence.\n"
            "- Include a 'Competing Perspectives' or 'Contradictions in Evidence' section if sources disagree.\n"
            "- Include a 'Data Gaps & Uncertainties' section listing indicators that were sought but not found or are unreliable.\n"
            "- Include a brief chronological timeline when significant events add context.\n"
            "- Cite sources inline using citation markers; do not invent new claims.\n"
            "- Use clean H2/H3 hierarchy; surface key stats in tables or bullets.\n"
        )
    deep_mode_rule = (
        "- Deep research mode: produce a comprehensive, multi-section response that fully develops the topic.\n"
        "- Deep research mode: use 6-10 substantive sections, each with 3-5 developed paragraphs.\n"
        "- Deep research mode: preserve source richness, cite heavily, and keep citation density high.\n"
        "- Deep research mode: do not collapse or summarize — expand and develop every section fully.\n"
        "- Deep research mode: include specific statistics, mechanisms, trade-offs, expert perspectives, and implications.\n"
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
        "- Develop each section fully: include specific data points, statistics, mechanisms, concrete examples, "
        "and implications. Never leave a section at a surface-level summary when the evidence supports more depth.\n"
        "- Put the delivered outcome first.\n"
        "- Open with a substantive paragraph that directly addresses the core finding or task outcome.\n"
        "- For research and analytical responses: develop 4-8 sections, each with 3-5 substantive paragraphs "
        "that explore different dimensions — do not collapse the answer into a brief overview.\n"
        "- When numeric or time-series data is available, surface it explicitly — in tables, with specific values.\n"
        "- When sources agree or conflict, call it out explicitly with specifics.\n"
        "- Adapt section structure and ordering to the request and blueprint.\n"
        "- Use precise, authoritative language at senior-analyst depth; write as if briefing an executive who needs the full picture.\n"
        "- Keep section headings specific, substantive, and high-signal.\n"
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
    response_max_tokens = 8000 if deep_research_mode else 6000
    polished = call_text_response(
        system_prompt=(
            "You are Maia's response writer — a research-grade analyst and expert communicator. "
            "Produce deep, substantive, well-structured answers that go beyond surface summaries. "
            "Surface specific data, explain mechanisms, compare perspectives, and develop each section fully. "
            f"{language_rule} "
            "Preserve all factual content exactly."
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
    raw_has_markdown_table = "|---|" in raw_answer
    cleaned_has_markdown_table = ("|---|" in cleaned) or ("<table" in cleaned.lower())
    if raw_has_markdown_table and not cleaned_has_markdown_table:
        return fallback_answer or raw_answer
    if "### GA4 Full Report Snapshot" in raw_answer and "### GA4 Full Report Snapshot" not in cleaned:
        return fallback_answer or raw_answer
    if len(cleaned) > int(target_max_chars * 1.35):
        return fallback_answer or raw_answer

    citation_tail = extract_citation_tail(raw_answer)
    if citation_tail and not contains_citation_markers(cleaned):
        cleaned = f"{cleaned}\n\n{citation_tail}".strip()

    cleaned = strip_wrapping_markdown_fence(cleaned)
    cleaned = normalize_citation_anchor_attrs(cleaned)
    cleaned = dedupe_terminal_sections(cleaned)
    cleaned = strip_noise_sections(cleaned, keep_diagnostics=keep_diagnostics)
    cleaned = strip_redundant_evidence_suffix(cleaned)
    cleaned = redact_emails(cleaned, emails=request_emails)
    if is_language_mismatch(
        request_message=request_message,
        requested_language=requested_language,
        candidate_text=cleaned,
        language_resolver=resolve_response_language,
        language_inferer=infer_user_language_code,
    ):
        return raw_answer
    return cleaned or raw_answer
