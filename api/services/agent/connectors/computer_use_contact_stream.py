from __future__ import annotations

from typing import Any, Generator

from .base import ConnectorError
from .computer_use_browser_helpers import (
    SUCCESS_TOKENS,
    VERIFICATION_TOKENS,
    build_contact_form_task,
    compact_text,
    token_match,
    write_snapshot,
)


def stream_contact_form_live(
    *,
    connector_user_id: str,
    url: str,
    sender_name: str,
    sender_email: str,
    sender_company: str = "",
    sender_phone: str = "",
    subject: str,
    message: str,
) -> Generator[dict[str, Any], None, dict[str, Any]]:
    clean_url = str(url or "").strip()
    if not clean_url:
        raise ConnectorError("A valid target URL is required for contact form submission.")
    if not str(message or "").strip():
        raise ConnectorError("A non-empty message is required for contact form submission.")

    from api.services.computer_use.agent_loop import run_agent_loop
    from api.services.computer_use.session_registry import get_session_registry

    registry = get_session_registry()
    session = registry.create(user_id=connector_user_id, start_url=clean_url)
    screenshot_path = ""
    transcript_rows: list[str] = []
    confirmation_text = ""
    human_handoff_required = False
    handoff_reason = ""
    handoff_type = ""
    event_index = 0
    try:
        session.navigate(clean_url)
        screenshot_path = write_snapshot(
            screenshot_b64=session.screenshot_b64(),
            label="contact-open",
        )
        yield {
            "event_type": "browser_open",
            "title": "Open target website for outreach",
            "detail": clean_url,
            "data": {"url": session.current_url(), "contact_target_url": session.current_url()},
            "snapshot_ref": screenshot_path,
        }
        yield {
            "event_type": "browser_contact_form_detected",
            "title": "Detect contact form",
            "detail": "Starting guided contact form completion",
            "data": {"url": session.current_url(), "contact_target_url": session.current_url()},
            "snapshot_ref": screenshot_path,
        }

        task = build_contact_form_task(
            url=clean_url,
            sender_name=sender_name,
            sender_email=sender_email,
            sender_company=sender_company,
            sender_phone=sender_phone,
            subject=subject,
            message=message,
        )
        for raw_event in run_agent_loop(session, task, max_iterations=14):
            event_index += 1
            event_type = str(raw_event.get("event_type") or "").strip().lower()
            if event_type == "screenshot":
                screenshot_path = write_snapshot(
                    screenshot_b64=str(raw_event.get("screenshot_b64") or ""),
                    label=f"contact-frame-{event_index}",
                )
                continue
            if event_type == "action":
                action_name = str(raw_event.get("action") or "action").strip().lower()
                mapped_type = "browser_contact_fill" if action_name in {"type", "key"} else "browser_contact_submit"
                yield {
                    "event_type": mapped_type,
                    "title": "Fill contact form" if mapped_type == "browser_contact_fill" else "Submit contact form",
                    "detail": action_name or "action",
                    "data": {"url": session.current_url(), "contact_target_url": session.current_url()},
                    "snapshot_ref": screenshot_path or None,
                }
                continue
            if event_type == "text":
                text = str(raw_event.get("text") or raw_event.get("detail") or "").strip()
                if text:
                    transcript_rows.append(text)
                    if token_match(text, VERIFICATION_TOKENS):
                        human_handoff_required = True
                        handoff_type = "captcha"
                        handoff_reason = "Human verification challenge detected."
                    if token_match(text, SUCCESS_TOKENS):
                        confirmation_text = text
                        yield {
                            "event_type": "browser_contact_confirmation",
                            "title": "Capture submission confirmation",
                            "detail": compact_text(text, limit=220),
                            "data": {"url": session.current_url(), "contact_target_url": session.current_url()},
                            "snapshot_ref": screenshot_path or None,
                        }
                continue
            if event_type == "error":
                detail = str(raw_event.get("detail") or "Contact form execution failed").strip()
                transcript_rows.append(detail)
                if token_match(detail, VERIFICATION_TOKENS):
                    human_handoff_required = True
                    handoff_type = "captcha"
                    handoff_reason = detail
                yield {
                    "event_type": "browser_interaction_failed",
                    "title": "Contact form execution failed",
                    "detail": compact_text(detail, limit=220),
                    "data": {"url": session.current_url(), "contact_target_url": session.current_url()},
                    "snapshot_ref": screenshot_path or None,
                }
                break
            if event_type in {"done", "max_iterations"}:
                break

        transcript = "\n\n".join(transcript_rows).strip()
        if not confirmation_text and token_match(transcript, SUCCESS_TOKENS):
            confirmation_text = compact_text(transcript, limit=280)
        submitted = bool(confirmation_text) and not human_handoff_required
        status = "submitted" if submitted else ("human_verification_required" if human_handoff_required else "submitted_unconfirmed")
        fields_filled = [
            key for key, val in {
                "name": sender_name,
                "email": sender_email,
                "company": sender_company,
                "phone": sender_phone,
                "subject": subject,
                "message": message,
            }.items() if str(val or "").strip()
        ]

        if human_handoff_required:
            yield {
                "event_type": "browser_contact_human_verification_required",
                "title": "Human verification required",
                "detail": handoff_reason or "Verification challenge detected on contact form.",
                "data": {
                    "url": session.current_url(),
                    "contact_target_url": session.current_url(),
                    "barrier_type": handoff_type or "captcha",
                },
                "snapshot_ref": screenshot_path or None,
            }
        yield {
            "event_type": "browser_contact_confirmation",
            "title": "Capture submission confirmation",
            "detail": confirmation_text or status,
            "data": {
                "url": session.current_url(),
                "contact_target_url": session.current_url(),
                "contact_status": status,
            },
            "snapshot_ref": screenshot_path or None,
        }

        try:
            title = session.page_title()
        except Exception:
            title = "Website Contact Form"
        return {
            "submitted": submitted,
            "status": status,
            "confirmation_text": confirmation_text,
            "url": session.current_url(),
            "title": title or "Website Contact Form",
            "fields_filled": fields_filled,
            "human_handoff_required": human_handoff_required,
            "handoff_reason": handoff_reason if human_handoff_required else "",
            "handoff_type": handoff_type if human_handoff_required else "",
            "navigated_contact_page": False,
        }
    except Exception as exc:
        raise ConnectorError(f"Contact form submission failed: {exc}") from exc
    finally:
        registry.close(session.session_id)
