from __future__ import annotations

from pathlib import Path
from typing import Any

from ..browser_live_utils import excerpt
from .capture import capture_page_state, move_cursor
from .detection import first_visible


def fill_contact_fields(
    *,
    page: Any,
    form: Any,
    sender_name: str,
    sender_email: str,
    subject: str,
    message: str,
    output_dir: Path,
    stamp_prefix: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    pending_events: list[dict[str, Any]] = []
    fields_filled: list[str] = []

    def _fill_field(
        *,
        selector_list: list[str],
        value: str,
        event_type: str,
        title: str,
        max_preview: int = 140,
    ) -> None:
        if not value.strip():
            return
        field = first_visible(form, selector_list)
        if field is None:
            return
        cursor = move_cursor(page=page, locator=field)
        try:
            field.click(timeout=3000)
            field.fill(value, timeout=4000)
        except Exception:
            return
        fields_filled.append(event_type.rsplit("_", 1)[-1])
        capture = capture_page_state(
            page=page,
            label=event_type,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
        )
        yield_payload = {
            "event_type": event_type,
            "title": title,
            "detail": excerpt(value, limit=max_preview),
            "data": {
                "url": capture["url"],
                "title": capture["title"],
                "contact_target_url": capture["url"],
                "typed_preview": value[:800],
                "field": event_type.rsplit("_", 1)[-1],
                **cursor,
            },
            "snapshot_ref": capture["screenshot_path"],
        }
        pending_events.append(yield_payload)

    _fill_field(
        selector_list=[
            "input[autocomplete='name']",
            "input[name='name' i]",
            "input[id*='name' i]",
            "input[placeholder*='name' i]",
        ],
        value=sender_name,
        event_type="browser_contact_fill_name",
        title="Fill contact name",
    )
    _fill_field(
        selector_list=[
            "input[type='email']",
            "input[name='email' i]",
            "input[id*='email' i]",
            "input[placeholder*='email' i]",
        ],
        value=sender_email,
        event_type="browser_contact_fill_email",
        title="Fill contact email",
    )
    _fill_field(
        selector_list=[
            "input[name*='subject' i]",
            "input[id*='subject' i]",
            "input[placeholder*='subject' i]",
            "input[name*='topic' i]",
        ],
        value=subject,
        event_type="browser_contact_fill_subject",
        title="Fill contact subject",
    )
    _fill_field(
        selector_list=[
            "textarea[name*='message' i]",
            "textarea[id*='message' i]",
            "textarea[placeholder*='message' i]",
            "textarea",
            "input[name*='message' i]",
            "input[id*='message' i]",
        ],
        value=message,
        event_type="browser_contact_fill_message",
        title="Fill contact message",
        max_preview=220,
    )
    return fields_filled, pending_events
