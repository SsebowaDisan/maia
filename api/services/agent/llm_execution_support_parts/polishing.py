from __future__ import annotations

import json

from api.services.agent.llm_runtime import call_json_response, env_bool


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
