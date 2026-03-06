from __future__ import annotations

import re
from typing import Any, Generator

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.llm_execution_support import polish_contact_form_content
from api.services.agent.llm_runtime import call_json_response
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolTraceEvent,
    ToolMetadata,
)

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def _resolve_url(prompt: str, params: dict[str, Any]) -> str:
    url = str(params.get("url") or "").strip()
    if not url:
        match = URL_RE.search(str(prompt or ""))
        url = match.group(0).strip() if match else ""
    return url


def _safe_text(value: Any, *, fallback: str, max_len: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        text = fallback
    if len(text) > max_len:
        text = f"{text[: max_len - 1].rstrip()}..."
    return text


def _normalize_phone(value: str) -> str:
    text = " ".join(str(value or "").split()).strip(" .,;:-")
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) < 7:
        return ""
    return text[:48]


def _infer_sender_name_from_email(email: str) -> str:
    token = " ".join(str(email or "").split()).strip()
    match = EMAIL_RE.search(token)
    if not match:
        return ""
    local_part = match.group(1).split("@", 1)[0].strip().lower()
    if not local_part:
        return ""
    chunks = [row for row in re.split(r"[._-]+", local_part) if row]
    if not chunks:
        return ""
    normalized_chunks: list[str] = []
    for chunk in chunks[:3]:
        cleaned = re.sub(r"[^a-z0-9]", "", chunk)
        cleaned = re.sub(r"\d+$", "", cleaned)
        if len(cleaned) < 2:
            continue
        normalized_chunks.append(cleaned[:24].capitalize())
    if not normalized_chunks:
        return ""
    return " ".join(normalized_chunks)[:120]


def _infer_sender_profile_from_prompt(prompt: str) -> dict[str, str]:
    clean_prompt = " ".join(str(prompt or "").split()).strip()
    if not clean_prompt:
        return {}
    try:
        response = call_json_response(
            system_prompt=(
                "You extract sender identity fields for enterprise contact-form automation. "
                "Return strict JSON only and never invent values."
            ),
            user_prompt=(
                "Extract sender details from this task text.\n"
                "Return JSON only:\n"
                '{ "sender_name":"", "sender_email":"", "sender_phone":"", "sender_company":"" }\n'
                "Rules:\n"
                "- Use only values explicitly provided by the user.\n"
                "- If a field is not explicitly provided, return empty string for that field.\n\n"
                f"Task:\n{clean_prompt}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=180,
        )
    except Exception:
        return {}
    if not isinstance(response, dict):
        return {}
    return {
        "sender_name": " ".join(str(response.get("sender_name") or "").split()).strip()[:120],
        "sender_email": " ".join(str(response.get("sender_email") or "").split()).strip()[:180],
        "sender_phone": " ".join(str(response.get("sender_phone") or "").split()).strip()[:48],
        "sender_company": " ".join(str(response.get("sender_company") or "").split()).strip()[:120],
    }


class BrowserContactFormSendTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="browser.contact_form.send",
        action_class="execute",
        risk_level="high",
        required_permissions=["browser.write", "external.communication"],
        execution_policy="confirm_before_execute",
        description="Open a website, fill a contact form, and submit outreach message.",
    )

    def execute_stream(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> Generator[ToolTraceEvent, None, ToolExecutionResult]:
        url = _resolve_url(prompt, params)
        if not url:
            raise ToolExecutionError("A valid target URL is required for contact form submission.")

        base_sender_name = params.get("sender_name") or context.settings.get("agent.contact_sender_name")
        base_sender_email = (
            params.get("sender_email")
            or context.settings.get("agent.contact_sender_email")
            or context.settings.get("MAIA_GMAIL_FROM")
        )
        base_sender_phone = (
            params.get("sender_phone")
            or context.settings.get("agent.contact_sender_phone")
            or context.settings.get("agent.contact_phone")
        )
        base_sender_company = params.get("sender_company") or context.settings.get("agent.contact_sender_company")
        inferred_sender = (
            {}
            if (base_sender_name and base_sender_email and base_sender_phone)
            else _infer_sender_profile_from_prompt(prompt)
        )
        sender_email = _safe_text(
            base_sender_email
            or inferred_sender.get("sender_email"),
            fallback="",
            max_len=180,
        )
        if not EMAIL_RE.search(sender_email):
            raise ToolExecutionError(
                "Sender email address is required for contact form submission."
            )
        sender_name = _safe_text(
            base_sender_name
            or inferred_sender.get("sender_name")
            or _infer_sender_name_from_email(sender_email),
            fallback="",
            max_len=120,
        )
        if not sender_name:
            raise ToolExecutionError(
                "Sender full name is required for contact form submission."
            )
        sender_company = _safe_text(
            base_sender_company
            or inferred_sender.get("sender_company"),
            fallback="",
            max_len=120,
        )
        sender_phone = _safe_text(
            base_sender_phone
            or inferred_sender.get("sender_phone"),
            fallback="",
            max_len=48,
        )
        sender_phone = _normalize_phone(sender_phone)
        raw_subject = _safe_text(
            params.get("subject"),
            fallback="Business Inquiry",
            max_len=180,
        )
        raw_message = _safe_text(
            params.get("message") or prompt,
            fallback="Hello, I would like to discuss a possible business collaboration.",
            max_len=900,
        )
        polished = polish_contact_form_content(
            subject=raw_subject,
            message_text=raw_message,
            website_url=url,
            context_summary=str(context.settings.get("__latest_report_title") or "").strip(),
        )
        subject = _safe_text(polished.get("subject"), fallback=raw_subject, max_len=180)
        message = _safe_text(polished.get("message_text"), fallback=raw_message, max_len=900)

        connector = get_connector_registry().build("playwright_contact_form", settings=context.settings)
        trace_events: list[ToolTraceEvent] = []
        stream = connector.submit_contact_form_live_stream(
            url=url,
            sender_name=sender_name,
            sender_email=sender_email,
            sender_company=sender_company,
            sender_phone=sender_phone,
            subject=subject,
            message=message,
            auto_accept_cookies=bool(params.get("auto_accept_cookies", True)),
        )
        while True:
            try:
                payload = next(stream)
            except StopIteration as stop:
                result_payload = stop.value
                break
            event = ToolTraceEvent(
                event_type=str(payload.get("event_type") or "browser_progress"),
                title=str(payload.get("title") or "Contact form activity"),
                detail=str(payload.get("detail") or ""),
                data=dict(payload.get("data") or {}),
                snapshot_ref=str(payload.get("snapshot_ref") or "") or None,
            )
            trace_events.append(event)
            yield event

        if not isinstance(result_payload, dict):
            raise ToolExecutionError("Contact form submission failed: missing result payload.")
        submitted = bool(result_payload.get("submitted"))
        status = str(result_payload.get("status") or "submitted_unconfirmed").strip()
        confirmation_text = str(result_payload.get("confirmation_text") or "").strip()
        final_url = str(result_payload.get("url") or url).strip()
        title = str(result_payload.get("title") or "Website Contact Form").strip() or "Website Contact Form"
        fields_filled = result_payload.get("fields_filled")
        if not isinstance(fields_filled, list):
            fields_filled = []

        context.settings["__latest_contact_form_submission"] = {
            "submitted": submitted,
            "status": status,
            "url": final_url,
            "sender_company": sender_company,
            "sender_phone": sender_phone,
            "subject": subject,
            "message_preview": message[:280],
            "confirmation_text": confirmation_text[:280],
        }

        summary = (
            f"Submitted contact form on {final_url}."
            if submitted
            else f"Contact form submitted on {final_url} (confirmation not explicit)."
        )
        content_lines = [
            "## Contact Form Submission",
            f"- Target URL: {final_url}",
            f"- Sender: {sender_name} <{sender_email}>",
            f"- Company: {sender_company or 'n/a'}",
            f"- Phone: {sender_phone or 'n/a'}",
            f"- Subject: {subject}",
            f"- Status: {status}",
            f"- Fields filled: {', '.join(str(item) for item in fields_filled) or 'n/a'}",
        ]
        if confirmation_text:
            content_lines.append(f"- Confirmation evidence: {confirmation_text}")
        next_steps = [
            "Review theatre replay to confirm field mapping and final confirmation text.",
            "If no clear confirmation appears, verify manually on the website inbox/contact channel.",
        ]
        if submitted:
            next_steps.insert(0, "Track outreach in Google Sheets and continue follow-up sequence.")

        return ToolExecutionResult(
            summary=summary,
            content="\n".join(content_lines),
            data={
                "submitted": submitted,
                "status": status,
                "url": final_url,
                "title": title,
                "sender_company": sender_company,
                "sender_phone": sender_phone,
                "subject": subject,
                "message_preview": message[:280],
                "confirmation_text": confirmation_text,
                "fields_filled": fields_filled,
            },
            sources=[
                AgentSource(
                    source_type="web",
                    label=title,
                    url=final_url,
                    score=0.78 if submitted else 0.6,
                    metadata={"contact_form_submission": True, "status": status},
                )
            ],
            next_steps=next_steps,
            events=trace_events,
        )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        stream = self.execute_stream(context=context, prompt=prompt, params=params)
        traces: list[ToolTraceEvent] = []
        while True:
            try:
                traces.append(next(stream))
            except StopIteration as stop:
                result = stop.value
                break
        result.events = traces
        return result
