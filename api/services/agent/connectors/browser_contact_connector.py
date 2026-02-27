from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Generator

from .browser_live_utils import excerpt
from .browser_navigation_utils import accept_cookie_banner
from .base import BaseConnector, ConnectorError, ConnectorHealth


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
        if "@" not in str(sender_email or ""):
            raise ConnectorError("A valid sender email is required for contact form submission.")
        if not str(message or "").strip():
            raise ConnectorError("A non-empty message is required for contact form submission.")

        from playwright.sync_api import Locator, Page, sync_playwright

        output_dir = Path(".maia_agent") / "browser_captures"
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp_prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

        def _capture_page_state(*, page: Page, label: str) -> dict[str, str]:
            safe_label = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in label)[:40]
            suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
            screenshot_path = output_dir / f"{stamp_prefix}-{safe_label}-{suffix}.png"
            page.screenshot(path=str(screenshot_path), full_page=False)
            return {
                "url": str(page.url or ""),
                "title": str(page.title() or ""),
                "screenshot_path": str(screenshot_path.resolve()),
            }

        def _move_cursor(*, page: Page, locator: Locator | None = None, x: float = 120, y: float = 120) -> dict[str, float]:
            cursor_x = float(x)
            cursor_y = float(y)
            if locator is not None:
                try:
                    box = locator.bounding_box()
                    if box:
                        cursor_x = float(box.get("x", cursor_x)) + min(80.0, float(box.get("width", 0.0)) / 2.0)
                        cursor_y = float(box.get("y", cursor_y)) + min(16.0, float(box.get("height", 0.0)) / 2.0)
                except Exception:
                    pass
            try:
                page.mouse.move(cursor_x, cursor_y, steps=14)
            except Exception:
                pass
            viewport = page.viewport_size or {"width": 1366, "height": 768}
            width = max(1.0, float(viewport.get("width") or 1366.0))
            height = max(1.0, float(viewport.get("height") or 768.0))
            return {
                "cursor_x": round((cursor_x / width) * 100.0, 2),
                "cursor_y": round((cursor_y / height) * 100.0, 2),
            }

        def _first_visible(scope: Page | Locator, selectors: list[str]) -> Locator | None:
            for selector in selectors:
                try:
                    loc = scope.locator(selector)
                    if loc.count() <= 0:
                        continue
                    candidate = loc.first
                    if hasattr(candidate, "is_visible") and not candidate.is_visible():
                        continue
                    return candidate
                except Exception:
                    continue
            return None

        def _locate_contact_form(page: Page) -> tuple[Locator | None, bool]:
            try:
                forms = page.locator("form")
                total = min(forms.count(), 12)
            except Exception:
                total = 0
            for idx in range(total):
                form = forms.nth(idx)
                try:
                    has_email = form.locator(
                        "input[type='email'], input[name*='email' i], input[id*='email' i]"
                    ).count() > 0
                    has_message = form.locator(
                        "textarea, input[name*='message' i], input[id*='message' i], textarea[name*='message' i]"
                    ).count() > 0
                    has_submit = form.locator(
                        "button[type='submit'], input[type='submit'], button:has-text('Send'), "
                        "button:has-text('Submit'), button:has-text('Contact'), button:has-text('Get in touch')"
                    ).count() > 0
                    if has_email and (has_message or has_submit):
                        return form, False
                except Exception:
                    continue

            contact_link = _first_visible(
                page,
                [
                    "a[href*='contact' i]",
                    "a:has-text('Contact')",
                    "a:has-text('Get in touch')",
                    "a:has-text('Reach us')",
                ],
            )
            if contact_link is None:
                return None, False
            try:
                contact_link.click(timeout=3500)
                page.wait_for_timeout(max(300, wait_ms))
            except Exception:
                return None, False
            try:
                forms = page.locator("form")
                total = min(forms.count(), 12)
            except Exception:
                total = 0
            for idx in range(total):
                form = forms.nth(idx)
                try:
                    has_email = form.locator(
                        "input[type='email'], input[name*='email' i], input[id*='email' i]"
                    ).count() > 0
                    has_message = form.locator(
                        "textarea, input[name*='message' i], input[id*='message' i], textarea[name*='message' i]"
                    ).count() > 0
                    if has_email and has_message:
                        return form, True
                except Exception:
                    continue
            return None, True

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(250, wait_ms))
            except Exception as exc:
                browser.close()
                raise ConnectorError(f"Failed to open URL: {url}. {exc}") from exc

            open_capture = _capture_page_state(page=page, label="contact-open")
            yield {
                "event_type": "browser_open",
                "title": "Open target website for outreach",
                "detail": open_capture["url"],
                "data": {
                    "url": open_capture["url"],
                    "title": open_capture["title"],
                    "contact_target_url": open_capture["url"],
                    **_move_cursor(page=page, x=118, y=88),
                },
                "snapshot_ref": open_capture["screenshot_path"],
            }

            if auto_accept_cookies:
                consent = accept_cookie_banner(page=page, wait_ms=wait_ms)
                consent_capture = _capture_page_state(page=page, label="contact-cookie")
                if consent.get("accepted"):
                    yield {
                        "event_type": "browser_cookie_accept",
                        "title": "Accept website cookies",
                        "detail": str(consent.get("label") or "Accepted cookie consent banner"),
                        "data": {
                            "url": consent_capture["url"],
                            "title": consent_capture["title"],
                            "contact_target_url": consent_capture["url"],
                        },
                        "snapshot_ref": consent_capture["screenshot_path"],
                    }

            form, navigated_contact_page = _locate_contact_form(page)
            detect_capture = _capture_page_state(page=page, label="contact-detected")
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
                field = _first_visible(form, selector_list)
                if field is None:
                    return
                cursor = _move_cursor(page=page, locator=field)
                try:
                    field.click(timeout=3000)
                    field.fill(value, timeout=4000)
                except Exception:
                    return
                fields_filled.append(event_type.rsplit("_", 1)[-1])
                capture = _capture_page_state(page=page, label=event_type)
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

            pending_events: list[dict[str, Any]] = []
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
            for payload in pending_events:
                yield payload

            submit_button = _first_visible(
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
                browser.close()
                raise ConnectorError("Contact form submit button could not be located.")

            submit_cursor = _move_cursor(page=page, locator=submit_button)
            try:
                submit_button.click(timeout=4500)
                page.wait_for_timeout(max(900, wait_ms))
                page.wait_for_load_state("networkidle", timeout=max(2500, timeout_ms // 2))
            except Exception:
                pass
            submit_capture = _capture_page_state(page=page, label="contact-submit")
            yield {
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
            submitted = any(re.search(pattern, page_text, flags=re.IGNORECASE) for pattern in confirmation_patterns)
            confirmation_text = excerpt(page_text, limit=220)
            confirm_capture = _capture_page_state(page=page, label="contact-confirm")
            yield {
                "event_type": "browser_contact_confirmation",
                "title": "Verify contact form confirmation",
                "detail": "Confirmation detected" if submitted else "No explicit confirmation text detected",
                "data": {
                    "url": confirm_capture["url"],
                    "title": confirm_capture["title"],
                    "contact_target_url": confirm_capture["url"],
                    "contact_status": "submitted" if submitted else "submitted_unconfirmed",
                    "confirmation_text": confirmation_text,
                },
                "snapshot_ref": confirm_capture["screenshot_path"],
            }
            browser.close()
            return {
                "submitted": submitted,
                "status": "submitted" if submitted else "submitted_unconfirmed",
                "confirmation_text": confirmation_text,
                "url": confirm_capture["url"],
                "title": confirm_capture["title"],
                "screenshot_path": confirm_capture["screenshot_path"],
                "fields_filled": fields_filled,
                "navigated_contact_page": navigated_contact_page,
            }
