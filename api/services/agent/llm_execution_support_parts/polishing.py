from __future__ import annotations

import json
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool
from api.services.agent.llm_execution_support_parts.polishing_text_utils import (
    EMAIL_RE,
    ends_with_fragment as _ends_with_fragment,
    inferred_focus_text as _inferred_focus_text,
    safe_trim_body as _safe_trim_body,
    sanitize_delivery_body as _sanitize_delivery_body,
    strip_embedded_email_draft as _strip_embedded_email_draft,
)

RESEARCH_INTENT_RE = re.compile(
    r"\b(research|analy(?:s|z)e|report|investigate|study|deep\s*research|overview)\b",
    re.I,
)
MARKDOWN_HEADING_LINE_RE = re.compile(r"(?im)^\s*#{1,6}\s+")


def _as_recipient_email_brief(*, body_text: str, objective: str) -> str:
    clean = _strip_embedded_email_draft(body_text=body_text)
    if not clean:
        clean = str(body_text or "").strip()
    lines: list[str] = []
    blank_pending = False
    for raw_line in clean.splitlines():
        line = str(raw_line or "").rstrip()
        stripped = line.strip()
        if not stripped:
            if lines and not blank_pending:
                lines.append("")
                blank_pending = True
            continue
        blank_pending = False
        if MARKDOWN_HEADING_LINE_RE.match(stripped):
            heading = re.sub(r"^\s*#{1,6}\s*", "", stripped).strip(" :")
            if heading:
                lines.append(f"{heading}:")
            continue
        if re.fullmatch(r"(?im)email\s*draft\s*:?\s*", stripped):
            continue
        lines.append(stripped)

    normalized = "\n".join(lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    if len(normalized) >= 120:
        return normalized[:4800]

    objective_line = " ".join(str(objective or "").split()).strip()
    if objective_line:
        if normalized:
            return f"{objective_line}\n\n{normalized}"[:4800]
        return objective_line[:4800]
    return normalized[:4800]


def _is_detailed_research_task(*, request_message: str, objective: str, sources: list[dict[str, Any]]) -> bool:
    if len(list(sources or [])) >= 3:
        return True
    merged = " ".join(str(part or "").strip() for part in (request_message, objective))
    return bool(RESEARCH_INTENT_RE.search(merged))


def _source_excerpt(row: dict[str, Any]) -> str:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    for key in ("phrase", "excerpt", "snippet", "note", "summary", "quote"):
        value = " ".join(str(metadata.get(key) or "").split()).strip()
        if value:
            return value[:220]
    return ""


def _fallback_template_recommendation(
    *,
    focus_label: str,
    detail_target: str,
) -> dict[str, Any]:
    sections: list[dict[str, str]] = [
        {"title": f"{focus_label}: Core Explanation", "purpose": "Answer the user question directly."},
        {
            "title": f"{focus_label}: Evidence and Findings",
            "purpose": "Summarize what was observed from sources and execution.",
        },
        {
            "title": "Practical Implications",
            "purpose": "Translate findings into practical impact, tradeoffs, and decisions.",
        },
        {
            "title": "Confidence and Limits",
            "purpose": "State evidence quality, uncertainty, and what remains unverified.",
        },
        {
            "title": "Recommended Next Actions",
            "purpose": "Provide clear, actionable follow-up steps.",
        },
    ]
    if detail_target != "detailed":
        sections = sections[:4]
    return {
        "template_name": "dynamic_research_brief",
        "rationale": "Balanced structure optimized for evidence-backed delivery.",
        "sections": sections,
        "detail_target": detail_target,
    }


def _delivery_length_target(*, detail_target: str, source_count: int) -> tuple[int, int]:
    if detail_target == "detailed":
        if source_count >= 12:
            return 4200, 9800
        if source_count >= 6:
            return 3200, 8600
        return 2200, 7000
    if source_count >= 6:
        return 1400, 3600
    return 900, 2800


def _recommend_delivery_template(
    *,
    request_message: str,
    objective: str,
    preferred_tone: str,
    detail_target: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    focus_label = _inferred_focus_text(request_message=request_message, objective=objective)
    fallback = _fallback_template_recommendation(
        focus_label=focus_label,
        detail_target=detail_target,
    )
    if not env_bool("MAIA_AGENT_LLM_DELIVERY_TEMPLATE_RECOMMENDER_ENABLED", default=True):
        return fallback

    source_signals = [
        {
            "label": " ".join(str(row.get("label") or "").split()).strip()[:120],
            "url": " ".join(str(row.get("url") or "").split()).strip()[:200],
            "source_type": " ".join(str(row.get("source_type") or "").split()).strip()[:40],
        }
        for row in list(sources or [])[:10]
        if isinstance(row, dict)
    ]
    payload = {
        "request_message": " ".join(str(request_message or "").split()).strip()[:700],
        "objective": " ".join(str(objective or "").split()).strip()[:500],
        "preferred_tone": " ".join(str(preferred_tone or "").split()).strip()[:80],
        "detail_target": detail_target,
        "source_signals": source_signals,
    }
    prompt = (
        "Recommend the best report template structure for this exact request.\n"
        "Return JSON only in this schema:\n"
        '{ "template_name": "string", "rationale": "string", "sections": ['
        '{"title":"string","purpose":"string"}], "detail_target": "standard|detailed" }\n'
        "Rules:\n"
        "- This recommendation is per prompt; do not use generic reusable section labels.\n"
        "- Section titles must reflect the user request topic.\n"
        "- Keep 4-6 sections maximum.\n"
        "- Favor clarity and high signal, with a premium concise tone.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You design report structures for high-quality executive communication. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=10,
        max_tokens=900,
    )
    if not isinstance(response, dict):
        return fallback

    template_name = " ".join(str(response.get("template_name") or "").split()).strip()[:80]
    rationale = " ".join(str(response.get("rationale") or "").split()).strip()[:240]
    response_detail = " ".join(str(response.get("detail_target") or "").split()).strip().lower()
    sections_raw = response.get("sections")
    clean_sections: list[dict[str, str]] = []
    if isinstance(sections_raw, list):
        for row in sections_raw[:6]:
            if not isinstance(row, dict):
                continue
            title = " ".join(str(row.get("title") or "").split()).strip()[:90]
            purpose = " ".join(str(row.get("purpose") or "").split()).strip()[:180]
            if title:
                clean_sections.append({"title": title, "purpose": purpose})
    if not template_name or len(clean_sections) < 3:
        return fallback

    return {
        "template_name": template_name,
        "rationale": rationale or fallback["rationale"],
        "sections": clean_sections,
        "detail_target": response_detail if response_detail in {"standard", "detailed"} else detail_target,
    }


def _fallback_delivery_draft(
    *,
    request_message: str,
    objective: str,
    report_title: str,
    executed_steps: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, str]:
    clean_objective = " ".join(str(objective or "").split()).strip()
    clean_request = " ".join(str(request_message or "").split()).strip()
    request_focus = clean_objective or clean_request or "the requested research task"
    focus_label = _inferred_focus_text(request_message=clean_request, objective=clean_objective)
    subject = " ".join(str(report_title or "").split()).strip() or "Research Report"

    successful_steps = [
        " ".join(str(row.get("summary") or row.get("title") or "").split()).strip()
        for row in list(executed_steps or [])
        if str(row.get("status") or "").strip().lower() == "success"
    ]
    successful_steps = [row for row in successful_steps if row][:6]

    source_lines: list[str] = []
    for source in list(sources or [])[:8]:
        label = " ".join(str(source.get("label") or "").split()).strip()
        url = " ".join(str(source.get("url") or "").split()).strip()
        excerpt = _source_excerpt(source)
        if label and url and excerpt:
            source_lines.append(f"- {label}: {url} | {excerpt}")
        elif label and url:
            source_lines.append(f"- {label}: {url}")
        elif label:
            source_lines.append(f"- {label}")
        elif url:
            source_lines.append(f"- {url}")
    source_lines = source_lines[:6]

    body_lines = [
        f"## {focus_label}: Research Overview",
        "",
        (
            f"This report addresses {request_focus}. "
            "The findings are based on the execution trace and captured source evidence."
        ),
        (
            "The objective was translated into concrete evidence collection, synthesis, and verification "
            "before delivery to the recipient."
        ),
        "",
        f"## {focus_label}: Evidence-Grounded Findings",
        "",
        (
            "The run prioritized source discovery, extraction of relevant facts, and consistency checks "
            "to reduce unsupported claims."
        ),
    ]
    if successful_steps:
        body_lines.extend(
            [
                "",
                "### Execution Highlights",
                "",
                *[f"{idx}. {item}" for idx, item in enumerate(successful_steps, start=1)],
            ]
        )
    if source_lines:
        body_lines.extend(["", "### Evidence Trail", "", *source_lines])
    body_lines.extend(
        [
            "",
            "### Interpretation",
            "",
            (
                "Current conclusions reflect only the validated material above. "
                "Where source coverage is partial, claims should be treated as directional rather than final."
            ),
        ]
    )
    body_lines.extend(
        [
            "",
            "### Recommended Next Actions",
            "",
            "- Confirm whether deeper domain coverage is required for any missing areas.",
            "- Approve a follow-up pass for additional primary sources if higher confidence is needed.",
        ]
    )
    return {"subject": subject, "body_text": "\n".join(body_lines).strip()}


def draft_delivery_report_content(
    *,
    request_message: str,
    objective: str,
    report_title: str,
    executed_steps: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    preferred_tone: str = "",
) -> dict[str, str]:
    fallback = _fallback_delivery_draft(
        request_message=request_message,
        objective=objective,
        report_title=report_title,
        executed_steps=executed_steps,
        sources=sources,
    )
    if not env_bool("MAIA_AGENT_LLM_DELIVERY_DRAFT_ENABLED", default=True):
        return fallback

    normalized_steps: list[dict[str, str]] = []
    for row in list(executed_steps or [])[:16]:
        if not isinstance(row, dict):
            continue
        normalized_steps.append(
            {
                "title": " ".join(str(row.get("title") or "").split()).strip()[:140],
                "status": " ".join(str(row.get("status") or "").split()).strip().lower()[:24],
                "tool_id": " ".join(str(row.get("tool_id") or "").split()).strip()[:120],
                "summary": " ".join(str(row.get("summary") or "").split()).strip()[:260],
            }
        )

    normalized_sources: list[dict[str, str]] = []
    for row in list(sources or [])[:16]:
        if not isinstance(row, dict):
            continue
        metadata = row.get("metadata")
        normalized_sources.append(
            {
                "label": " ".join(str(row.get("label") or "").split()).strip()[:180],
                "url": " ".join(str(row.get("url") or "").split()).strip()[:220],
                "source_type": " ".join(str(row.get("source_type") or "").split()).strip()[:40],
                "excerpt": (
                    " ".join(str(_source_excerpt({"metadata": metadata}) or "").split()).strip()[:240]
                ),
            }
        )

    detail_target = "detailed" if _is_detailed_research_task(
        request_message=request_message,
        objective=objective,
        sources=sources,
    ) else "standard"
    target_min_chars, target_max_chars = _delivery_length_target(
        detail_target=detail_target,
        source_count=len(normalized_sources),
    )
    template_recommendation = _recommend_delivery_template(
        request_message=request_message,
        objective=objective,
        preferred_tone=preferred_tone,
        detail_target=detail_target,
        sources=sources,
    )
    payload = {
        "request_message": " ".join(str(request_message or "").split()).strip()[:700],
        "objective": " ".join(str(objective or "").split()).strip()[:600],
        "report_title": " ".join(str(report_title or "").split()).strip()[:180],
        "preferred_tone": " ".join(str(preferred_tone or "").split()).strip()[:80],
        "detail_target": detail_target,
        "recommended_template": template_recommendation,
        "executed_steps": normalized_steps,
        "sources": normalized_sources,
    }
    prompt = (
        "Draft a delivery-ready research email report from the provided execution context.\n"
        "Return JSON only in this schema:\n"
        '{ "subject": "string", "body_text": "markdown string" }\n'
        "Rules:\n"
        "- Body must be clean markdown and directly answer the user's question.\n"
        "- Do not use a fixed reusable template; structure the report for this specific request.\n"
        "- Use request-specific section titles instead of boilerplate labels.\n"
        "- Follow the recommended_template as the primary structure guide for this prompt.\n"
        "- Keep 4-6 sections with clear hierarchy and premium readability.\n"
        "- Include a clear explanation, key mechanisms, practical implications, and risks/limitations where relevant.\n"
        "- Explicitly connect findings to the provided execution steps and source evidence.\n"
        "- Cite sources inline as markdown links whenever URLs are available.\n"
        "- If evidence is limited, state the limitation clearly without inventing facts.\n"
        "- Keep language professional, clear, and premium in tone (Apple-style clarity: simple, precise, confident).\n"
        f"- Target approximately {target_min_chars}-{target_max_chars} characters for the body.\n"
        "- Do not include recipient email addresses or internal system commentary.\n"
        "- Keep subject concise and relevant to the user request.\n\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )
    response = call_json_response(
        system_prompt=(
            "You write executive-quality outbound research report emails. "
            "Output strict JSON only."
        ),
        user_prompt=prompt,
        temperature=0.2,
        timeout_seconds=18,
        max_tokens=3000,
    )
    if not isinstance(response, dict):
        return fallback

    subject = " ".join(str(response.get("subject") or "").split()).strip()[:180]
    body_text = str(response.get("body_text") or "").strip()
    if not subject:
        subject = fallback["subject"]
    if not body_text:
        body_text = fallback["body_text"]

    clean_body = _sanitize_delivery_body(body_text=body_text, recipient="")
    clean_body = _safe_trim_body(clean_body, max_chars=12000)
    min_chars = target_min_chars
    if len(clean_body) < min_chars:
        clean_body = fallback["body_text"]
    elif len(clean_body) > int(target_max_chars * 1.35):
        clean_body = _safe_trim_body(clean_body, max_chars=target_max_chars)
    return {"subject": subject, "body_text": clean_body}


def polish_email_content(
    *,
    subject: str,
    body_text: str,
    recipient: str,
    context_summary: str = "",
    target_format: str = "report_markdown",
) -> dict[str, str]:
    if not env_bool("MAIA_AGENT_LLM_EMAIL_POLISH_ENABLED", default=True):
        return {"subject": subject, "body_text": _sanitize_delivery_body(body_text=body_text, recipient=recipient)}
    normalized_target = " ".join(str(target_format or "").split()).strip().lower()
    if normalized_target not in {"report_markdown", "recipient_email"}:
        normalized_target = "report_markdown"
    recipient_text = " ".join(str(recipient or "").split()).strip()
    sanitized_context = str(context_summary or "").strip()
    if recipient_text:
        sanitized_context = re.sub(re.escape(recipient_text), "", sanitized_context, flags=re.IGNORECASE)
        sanitized_context = " ".join(sanitized_context.split())
    baseline_body = _sanitize_delivery_body(body_text=body_text, recipient=recipient_text)
    baseline_body = _safe_trim_body(baseline_body, max_chars=12000)
    if normalized_target == "recipient_email":
        baseline_body = _as_recipient_email_brief(body_text=baseline_body, objective=sanitized_context)
    payload = {
        "recipient": recipient_text,
        "subject": str(subject or "").strip(),
        "body_text": baseline_body,
        "context_summary": sanitized_context,
        "target_format": normalized_target,
    }
    target_rules = (
        "- Output must be a clean outbound email body for a busy business recipient.\n"
        "- Use concise prose and bullet points where helpful.\n"
        "- Do not output markdown headings (no lines starting with #).\n"
        "- Do not include any section named 'Email Draft'.\n"
        "- Never include placeholders such as [Your Name], [Your Position], or [Your Contact Information].\n"
        "- Keep only recipient-facing content; remove internal planning/report scaffolding.\n"
    )
    if normalized_target != "recipient_email":
        target_rules = (
            "- Do not force a generic template; preserve or improve request-specific structure.\n"
            "- Keep section structure intact when the draft is report-like markdown.\n"
        )
    prompt = (
        "Polish this email draft for clarity and executive tone.\n"
        "Return JSON only in this schema:\n"
        '{ "subject": "string", "body_text": "string" }\n'
        "Rules:\n"
        "- Preserve factual content; do not invent claims.\n"
        "- Keep tone professional, complete, and premium in clarity.\n"
        "- Keep report depth intact; avoid over-compressing substantive content.\n"
        "- Do not include recipient email addresses in the message body.\n"
        "- Do not add placeholder recipient tokens such as bracketed names.\n"
        f"{target_rules}\n"
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
        max_tokens=2400,
    )
    if not isinstance(response, dict):
        return {"subject": subject, "body_text": baseline_body}
    clean_subject = " ".join(str(response.get("subject") or "").split()).strip()[:180]
    clean_body = str(response.get("body_text") or "").strip()
    if not clean_subject:
        clean_subject = str(subject or "").strip()
    if not clean_body:
        clean_body = baseline_body
    clean_body = _sanitize_delivery_body(body_text=clean_body, recipient=recipient_text)
    if normalized_target == "recipient_email":
        clean_body = _as_recipient_email_brief(body_text=clean_body, objective=sanitized_context)
        clean_body = _safe_trim_body(clean_body, max_chars=4800)
    else:
        clean_body = _safe_trim_body(clean_body, max_chars=12000)
    if normalized_target != "recipient_email" and baseline_body and len(baseline_body) >= 900:
        min_preserved = int(len(baseline_body) * 0.85)
        if len(clean_body) < min_preserved:
            clean_body = baseline_body
    if baseline_body and len(clean_body) < len(baseline_body) and _ends_with_fragment(clean_body):
        clean_body = baseline_body
    if normalized_target == "recipient_email" and len(clean_body) < 120:
        clean_body = baseline_body
    if not clean_body:
        clean_body = baseline_body
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
