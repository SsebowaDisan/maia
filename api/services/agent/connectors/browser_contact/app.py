from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Generator

from ..base import BaseConnector, ConnectorError, ConnectorHealth
from ..browser_navigation_utils import accept_cookie_banner
from .capture import capture_page_state, move_cursor
from .detection import locate_contact_form
from .fields import fill_contact_fields
from .submission import submit_and_confirm


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if not token:
        return default
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_float(
    value: Any,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    return max(float(minimum), min(float(maximum), parsed))


class BrowserContactConnector(BaseConnector):
    connector_id = "playwright_contact_form"

    def _playwright_available(self) -> bool:
        try:
            import playwright.sync_api  # noqa: F401

            return True
        except Exception:
            return False

    def health_check(self) -> ConnectorHealth:
        if not self._playwright_available():
            return ConnectorHealth(
                self.connector_id,
                False,
                "Playwright is not installed. Run `pip install playwright` and `playwright install`.",
            )
        return ConnectorHealth(self.connector_id, True, "configured")

    def submit_contact_form_live_stream(
        self,
        *,
        url: str,
        sender_name: str,
        sender_email: str,
        sender_company: str = "",
        sender_phone: str = "",
        subject: str,
        message: str,
        auto_accept_cookies: bool = True,
        timeout_ms: int = 25000,
        wait_ms: int = 1200,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        if not self._playwright_available():
            raise ConnectorError(
                "Playwright is not installed. Run `pip install playwright` and `playwright install`."
            )
        if not str(url or "").strip():
            raise ConnectorError("A valid target URL is required for contact form submission.")
        if not str(message or "").strip():
            raise ConnectorError("A non-empty message is required for contact form submission.")

        from playwright.sync_api import sync_playwright

        output_dir = Path(".maia_agent") / "browser_captures"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(250, wait_ms))
            except Exception as exc:
                browser.close()
                raise ConnectorError(f"Failed to open URL: {url}. {exc}") from exc

            open_capture = capture_page_state(
                page=page,
                label="contact-open",
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
            )
            yield {
                "event_type": "browser_open",
                "title": "Open target website for outreach",
                "detail": open_capture["url"],
                "data": {
                    "url": open_capture["url"],
                    "title": open_capture["title"],
                    "contact_target_url": open_capture["url"],
                    **move_cursor(page=page, x=118, y=88),
                },
                "snapshot_ref": open_capture["screenshot_path"],
            }

            if auto_accept_cookies:
                consent = accept_cookie_banner(page=page, wait_ms=wait_ms)
                consent_capture = capture_page_state(
                    page=page,
                    label="contact-cookie",
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                )
                if consent.get("accepted"):
                    consent_cursor = {
                        key: float(consent.get(key))
                        for key in ("cursor_x", "cursor_y")
                        if isinstance(consent.get(key), (int, float))
                    }
                    yield {
                        "event_type": "browser_cookie_accept",
                        "title": "Accept website cookies",
                        "detail": str(
                            consent.get("label") or "Accepted cookie consent banner"
                        ),
                        "data": {
                            "url": consent_capture["url"],
                            "title": consent_capture["title"],
                            "contact_target_url": consent_capture["url"],
                            **consent_cursor,
                        },
                        "snapshot_ref": consent_capture["screenshot_path"],
                    }

            form, navigated_contact_page, navigation_trace = locate_contact_form(
                page,
                wait_ms=wait_ms,
                timeout_ms=timeout_ms,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
            )
            for nav_event in navigation_trace:
                yield {
                    "event_type": str(nav_event.get("event_type") or "browser_navigate"),
                    "title": str(nav_event.get("title") or "Navigate website"),
                    "detail": str(nav_event.get("detail") or ""),
                    "data": dict(nav_event.get("data") or {}),
                    "snapshot_ref": str(nav_event.get("snapshot_ref") or "") or None,
                }
            detect_capture = capture_page_state(
                page=page,
                label="contact-detected",
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
            )
            if form is None:
                browser.close()
                raise ConnectorError(
                    "No contact form was detected on the website or contact page."
                )

            yield {
                "event_type": "browser_contact_form_detected",
                "title": "Detect contact form",
                "detail": "Contact form located and ready for typing",
                "data": {
                    "url": detect_capture["url"],
                    "title": detect_capture["title"],
                    "contact_target_url": detect_capture["url"],
                    "navigated_contact_page": navigated_contact_page,
                },
                "snapshot_ref": detect_capture["screenshot_path"],
            }

            fields_filled, fill_events = fill_contact_fields(
                page=page,
                form=form,
                sender_name=sender_name,
                sender_email=sender_email,
                sender_company=sender_company,
                sender_phone=sender_phone,
                subject=subject,
                message=message,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                enable_llm_fallback=_coerce_bool(
                    self.settings.get("agent.contact_form_llm_fallback_enabled")
                    or self.settings.get("MAIA_AGENT_CONTACT_FORM_LLM_FALLBACK_ENABLED")
                    or os.getenv("MAIA_AGENT_CONTACT_FORM_LLM_FALLBACK_ENABLED"),
                    default=True,
                ),
                llm_min_confidence=_coerce_float(
                    self.settings.get("agent.contact_form_llm_fallback_confidence")
                    or self.settings.get("MAIA_AGENT_CONTACT_FORM_LLM_FALLBACK_CONFIDENCE")
                    or os.getenv("MAIA_AGENT_CONTACT_FORM_LLM_FALLBACK_CONFIDENCE"),
                    default=0.68,
                    minimum=0.45,
                    maximum=0.98,
                ),
            )
            for payload in fill_events:
                yield payload

            submit_event, confirm_event, result = submit_and_confirm(
                page=page,
                form=form,
                fields_filled=fields_filled,
                wait_ms=wait_ms,
                timeout_ms=timeout_ms,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
            )
            yield submit_event
            yield confirm_event
            browser.close()
            result["navigated_contact_page"] = navigated_contact_page
            return result
