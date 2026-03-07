from __future__ import annotations

import json
import re

from api.services.agent.llm_runtime import call_json_response, env_bool
DEAR_PLACEHOLDER_RE = re.compile(r"(?im)^\s*dear\s*\[[^\]\n]{1,80}\]\s*,?\s*$")


def _sanitize_delivery_body(*, body_text: str, recipient: str) -> str:
    clean = str(body_text or "").strip()
    if not clean:
        return ""
    recipient_text = " ".join(str(recipient or "").split()).strip()
    if recipient_text:
        clean = re.sub(re.escape(recipient_text), "the recipient", clean, flags=re.IGNORECASE)
    clean = DEAR_PLACEHOLDER_RE.sub("Hello,", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def _safe_trim_body(text: str, *, max_chars: int = 12000) -> str:
    clean = str(text or "").strip()
    if len(clean) <= max_chars:
        return clean
    window = clean[: max_chars + 1]
    cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut < int(max_chars * 0.7):
        cut = max_chars
    return window[:cut].rstrip()


def _ends_with_fragment(text: str) -> bool:
    clean = str(text or "").rstrip()
    if not clean:
        return False
    if clean[-1] in ".!?:;)]}\"'":
        return False
    token_match = re.search(r"([A-Za-z]{1,2})\s*$", clean)
    return bool(token_match and len(clean) >= 240)


def polish_email_content(
    *,
    subject: str,
    body_text: str,
    recipient: str,
    context_summary: str = "",
) -> dict[str, str]:
    if not env_bool("MAIA_AGENT_LLM_EMAIL_POLISH_ENABLED", default=True):
        return {"subject": subject, "body_text": _sanitize_delivery_body(body_text=body_text, recipient=recipient)}
    recipient_text = " ".join(str(recipient or "").split()).strip()
    sanitized_context = str(context_summary or "").strip()
    if recipient_text:
        sanitized_context = re.sub(re.escape(recipient_text), "", sanitized_context, flags=re.IGNORECASE)
        sanitized_context = " ".join(sanitized_context.split())
    baseline_body = _sanitize_delivery_body(body_text=body_text, recipient=recipient_text)
    baseline_body = _safe_trim_body(baseline_body, max_chars=12000)
    payload = {
        "recipient": recipient_text,
        "subject": str(subject or "").strip(),
        "body_text": baseline_body,
        "context_summary": sanitized_context,
    }
    prompt = (
        "Polish this email draft for clarity and executive tone.\n"
        "Return JSON only in this schema:\n"
        '{ "subject": "string", "body_text": "string" }\n'
        "Rules:\n"
        "- Preserve factual content; do not invent claims.\n"
        "- Keep tone professional, concise, and complete.\n"
        "- Do not include recipient email addresses in the message body.\n"
        "- Do not add placeholder recipient tokens such as bracketed names.\n"
        "- Keep section structure intact when the draft is report-like markdown.\n\n"
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
        return {"subject": subject, "body_text": _sanitize_delivery_body(body_text=body_text, recipient=recipient_text)}
    clean_subject = " ".join(str(response.get("subject") or "").split()).strip()[:180]
    clean_body = str(response.get("body_text") or "").strip()
    if not clean_subject:
        clean_subject = str(subject or "").strip()
    if not clean_body:
        clean_body = baseline_body
    clean_body = _sanitize_delivery_body(body_text=clean_body, recipient=recipient_text)
    clean_body = _safe_trim_body(clean_body, max_chars=12000)
    if baseline_body and len(baseline_body) >= 1600:
        min_preserved = int(len(baseline_body) * 0.72)
        if len(clean_body) < min_preserved:
            clean_body = baseline_body
    if baseline_body and len(clean_body) < len(baseline_body) and _ends_with_fragment(clean_body):
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
