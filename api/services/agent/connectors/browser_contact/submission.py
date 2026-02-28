from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..base import ConnectorError
from ..browser_live_utils import excerpt
from .capture import capture_page_state, move_cursor
from .detection import first_visible


def submit_and_confirm(
    *,
    page: Any,
    form: Any,
    fields_filled: list[str],
    wait_ms: int,
    timeout_ms: int,
    output_dir: Path,
    stamp_prefix: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    submit_button = first_visible(
        form,
        [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Send')",
            "button:has-text('Submit')",
            "button:has-text('Contact')",
            "button:has-text('Get in touch')",
        ],
    )
    if submit_button is None:
        raise ConnectorError("Contact form submit button could not be located.")

    submit_cursor = move_cursor(page=page, locator=submit_button)
    try:
        submit_button.click(timeout=4500)
        page.wait_for_timeout(max(900, wait_ms))
        page.wait_for_load_state("networkidle", timeout=max(2500, timeout_ms // 2))
    except Exception:
        pass
    submit_capture = capture_page_state(
        page=page,
        label="contact-submit",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    submit_event = {
        "event_type": "browser_contact_submit",
        "title": "Submit contact form",
        "detail": "Submitted website contact form",
        "data": {
            "url": submit_capture["url"],
            "title": submit_capture["title"],
            "contact_target_url": submit_capture["url"],
            "fields_filled": fields_filled,
            **submit_cursor,
        },
        "snapshot_ref": submit_capture["screenshot_path"],
    }

    try:
        page_text = str(page.evaluate("() => document.body ? document.body.innerText : ''") or "")
    except Exception:
        page_text = ""
    confirmation_patterns = (
        r"\bthank you\b",
        r"\bmessage (?:has been )?sent\b",
        r"\bwe(?:'ll| will) (?:get|be) in touch\b",
        r"\bsubmission (?:received|successful)\b",
        r"\byour inquiry\b",
    )
    submitted = any(
        re.search(pattern, page_text, flags=re.IGNORECASE)
        for pattern in confirmation_patterns
    )
    confirmation_text = excerpt(page_text, limit=220)
    confirm_capture = capture_page_state(
        page=page,
        label="contact-confirm",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    confirm_event = {
        "event_type": "browser_contact_confirmation",
        "title": "Verify contact form confirmation",
        "detail": (
            "Confirmation detected"
            if submitted
            else "No explicit confirmation text detected"
        ),
        "data": {
            "url": confirm_capture["url"],
            "title": confirm_capture["title"],
            "contact_target_url": confirm_capture["url"],
            "contact_status": "submitted" if submitted else "submitted_unconfirmed",
            "confirmation_text": confirmation_text,
        },
        "snapshot_ref": confirm_capture["screenshot_path"],
    }
    return submit_event, confirm_event, {
        "submitted": submitted,
        "status": "submitted" if submitted else "submitted_unconfirmed",
        "confirmation_text": confirmation_text,
        "url": confirm_capture["url"],
        "title": confirm_capture["title"],
        "screenshot_path": confirm_capture["screenshot_path"],
        "fields_filled": fields_filled,
    }
