from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

SUCCESS_TOKENS = (
    "thank you",
    "thanks for",
    "message sent",
    "submitted",
    "we will get back",
    "we'll get back",
    "received your message",
    "your message has been sent",
)
VERIFICATION_TOKENS = (
    "captcha",
    "verify you are human",
    "security verification",
    "cloudflare",
    "turnstile",
    "recaptcha",
    "access denied",
    "challenge",
)


def compact_text(value: Any, *, limit: int = 200) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)].rstrip()}..."


def token_match(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in tokens)


def build_browse_task(
    *,
    url: str,
    max_pages: int,
    max_scroll_steps: int,
    follow_same_domain_links: bool,
    interaction_actions: list[dict[str, Any]] | None,
) -> str:
    base = (
        f"Open {url}. Inspect visible content and extract key text findings. "
        f"Scroll up to {max(1, int(max_scroll_steps))} times to reveal lazy content."
    )
    if follow_same_domain_links:
        base += f" Follow up to {max(1, int(max_pages))} relevant links on the same domain."
    actions = interaction_actions if isinstance(interaction_actions, list) else []
    if actions:
        action_rows = [
            f"- {str(row.get('type') or 'action')}: {str(row.get('selector') or row.get('text') or '')}".strip()
            for row in actions[:8]
        ]
        base += " Perform these requested interactions when safe:\n" + "\n".join(action_rows)
    base += " Finish by reporting concise factual findings from the page."
    return base


def build_contact_form_task(
    *,
    url: str,
    sender_name: str,
    sender_email: str,
    sender_company: str,
    sender_phone: str,
    subject: str,
    message: str,
) -> str:
    return (
        f"Open {url}. Find the contact form and fill these fields exactly when matching fields exist: "
        f"name='{sender_name}', email='{sender_email}', company='{sender_company}', phone='{sender_phone}', "
        f"subject='{subject}', message='{message}'. Submit the form. "
        "Then report the exact confirmation text shown on the page. "
        "If a captcha or human verification appears, report that clearly."
    )


def quality_profile(*, text: str, error_text: str) -> dict[str, Any]:
    combined = " ".join(part for part in [str(text or ""), str(error_text or "")] if part).strip().lower()
    words = len(re.findall(r"[A-Za-z0-9]+", combined))
    density = round(min(1.0, float(words) / 420.0), 4)
    blocked_reason = "bot_challenge" if token_match(combined, VERIFICATION_TOKENS) else ""
    blocked_signal = bool(blocked_reason)
    if blocked_signal:
        render_quality = "blocked"
    elif words < 40:
        render_quality = "low"
    elif words < 180:
        render_quality = "medium"
    else:
        render_quality = "high"
    return {
        "render_quality": render_quality,
        "content_density": density,
        "blocked_signal": blocked_signal,
        "blocked_reason": blocked_reason,
    }


def write_snapshot(*, screenshot_b64: str, label: str) -> str:
    encoded = str(screenshot_b64 or "").strip()
    if not encoded:
        return ""
    output_dir = Path(".maia_agent") / "browser_captures"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    file_path = output_dir / f"cu-{label}-{stamp}.png"
    try:
        file_path.write_bytes(base64.b64decode(encoded))
        return str(file_path.resolve())
    except Exception:
        return ""


def cursor_payload(raw_event: dict[str, Any]) -> dict[str, float]:
    event_input = raw_event.get("input")
    if not isinstance(event_input, dict):
        return {}
    coordinate = event_input.get("coordinate")
    if not isinstance(coordinate, list) or len(coordinate) < 2:
        return {}
    try:
        x = float(coordinate[0])
        y = float(coordinate[1])
    except Exception:
        return {}
    return {
        "cursor_x": round(max(0.0, min(100.0, (x / 1280.0) * 100.0)), 2),
        "cursor_y": round(max(0.0, min(100.0, (y / 800.0) * 100.0)), 2),
    }
