from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import re
from typing import Any, Generator

from .base import BaseConnector, ConnectorError, ConnectorHealth


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _safe_label(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip())
    return clean.strip("-")[:48] or "scene"


class GmailPlaywrightConnector(BaseConnector):
    connector_id = "gmail_playwright"

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

    def _capture(self, *, page: Any, output_dir: Path, stamp: str, label: str) -> dict[str, str]:
        suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
        filename = f"{stamp}-{_safe_label(label)}-{suffix}.png"
        path = output_dir / filename
        page.screenshot(path=str(path), full_page=False)
        title = ""
        try:
            title = str(page.title() or "").strip()
        except Exception:
            title = ""
        return {
            "snapshot_ref": str(path.resolve()),
            "url": str(page.url or "").strip(),
            "title": title,
        }

    def _viewport_size(self, *, page: Any) -> tuple[float, float]:
        try:
            raw = page.evaluate(
                "() => ({ w: Number(window.innerWidth || 1366), h: Number(window.innerHeight || 860) })"
            )
            width = float((raw or {}).get("w") or 1366)
            height = float((raw or {}).get("h") or 860)
            return max(1.0, width), max(1.0, height)
        except Exception:
            return 1366.0, 860.0

    def _cursor_payload(self, *, page: Any, x: float, y: float) -> dict[str, float]:
        width, height = self._viewport_size(page=page)
        return {
            "cursor_x": round((float(x) / width) * 100.0, 2),
            "cursor_y": round((float(y) / height) * 100.0, 2),
        }

    def _move_to_locator(self, *, page: Any, locator: Any, timeout_ms: int) -> dict[str, float]:
        try:
            box = locator.bounding_box(timeout=timeout_ms)
        except Exception:
            box = None
        if isinstance(box, dict):
            x = float(box.get("x") or 0.0) + float(box.get("width") or 0.0) / 2.0
            y = float(box.get("y") or 0.0) + float(box.get("height") or 0.0) / 2.0
            try:
                page.mouse.move(x, y, steps=18)
            except Exception:
                pass
            return self._cursor_payload(page=page, x=x, y=y)
        return {}

    def _first_visible(self, *, page: Any, selectors: list[str]) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() <= 0:
                    continue
                if locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    def _looks_like_login(self, *, page: Any) -> bool:
        url = str(page.url or "").lower()
        if "accounts.google.com" in url or "signin" in url:
            return True
        probes = [
            "input[type='email']",
            "input[type='password']",
            "button:has-text('Next')",
            "button:has-text('Sign in')",
            "div:has-text('Use your Google Account')",
        ]
        for selector in probes:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _open_mail_via_search(self, *, page: Any, timeout_ms: int, wait_ms: int) -> None:
        page.goto("https://www.bing.com/", wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(wait_ms)
        search_input = self._first_visible(
            page=page,
            selectors=[
                "textarea[name='q']",
                "input[name='q']",
                "input[type='search']",
            ],
        )
        if search_input is None:
            page.goto("https://mail.google.com/mail/u/0/#inbox?compose=new", timeout=timeout_ms)
            page.wait_for_timeout(wait_ms)
            return
        search_input.click(timeout=timeout_ms)
        search_input.fill("gmail", timeout=timeout_ms)
        search_input.press("Enter", timeout=timeout_ms)
        page.wait_for_timeout(wait_ms)

        open_result = False
        link_selectors = [
            "a[href*='mail.google.com']",
            "li.b_algo a[href*='mail.google.com']",
            "a:has-text('Gmail')",
        ]
        for selector in link_selectors:
            try:
                link = page.locator(selector).first
                if link.count() <= 0:
                    continue
                link.click(timeout=timeout_ms)
                open_result = True
                break
            except Exception:
                continue
        if not open_result:
            page.goto("https://mail.google.com/mail/u/0/#inbox?compose=new", timeout=timeout_ms)
        page.wait_for_timeout(wait_ms)

    def _ensure_compose_open(self, *, page: Any, timeout_ms: int, wait_ms: int) -> None:
        to_field = self._first_visible(
            page=page,
            selectors=[
                "textarea[name='to']",
                "input[aria-label='To recipients']",
                "input[aria-label*='To']",
            ],
        )
        if to_field is not None:
            return
        compose_button = self._first_visible(
            page=page,
            selectors=[
                "div[role='button'][gh='cm']",
                "div[role='button'][data-tooltip*='Compose']",
                "div[role='button']:has-text('Compose')",
                "button:has-text('Compose')",
            ],
        )
        if compose_button is None:
            raise ConnectorError(
                "Unable to open Gmail compose window. Compose button or recipient field not found."
            )
        compose_button.click(timeout=timeout_ms)
        page.wait_for_timeout(wait_ms)
        to_field = self._first_visible(
            page=page,
            selectors=[
                "textarea[name='to']",
                "input[aria-label='To recipients']",
                "input[aria-label*='To']",
            ],
        )
        if to_field is None:
            raise ConnectorError("Gmail compose opened, but recipient field was not found.")

    def compose_live_stream(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        send: bool,
        timeout_ms: int = 30000,
        wait_ms: int = 1200,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        if not self._playwright_available():
            raise ConnectorError(
                "Playwright is not installed. Run `pip install playwright` and `playwright install`."
            )
        to_text = str(to or "").strip()
        if not to_text:
            raise ConnectorError("Recipient is required for Gmail desktop compose.")

        from playwright.sync_api import sync_playwright

        output_dir = Path(".maia_agent") / "browser_captures"
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_dir = Path(
            str(
                self.settings.get("AGENT_GMAIL_PLAYWRIGHT_PROFILE_DIR")
                or os.getenv("AGENT_GMAIL_PLAYWRIGHT_PROFILE_DIR")
                or (Path(".maia_agent") / "playwright" / "gmail_profile")
            )
        ).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)

        headless = _truthy(
            self.settings.get("AGENT_GMAIL_PLAYWRIGHT_HEADLESS")
            or os.getenv("AGENT_GMAIL_PLAYWRIGHT_HEADLESS"),
            default=True,
        )
        slow_mo_raw = self.settings.get("AGENT_GMAIL_PLAYWRIGHT_SLOW_MO_MS") or os.getenv(
            "AGENT_GMAIL_PLAYWRIGHT_SLOW_MO_MS", "50"
        )
        try:
            slow_mo = max(0, int(str(slow_mo_raw).strip()))
        except Exception:
            slow_mo = 50

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=headless,
                slow_mo=slow_mo,
                viewport={"width": 1366, "height": 860},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()

            self._open_mail_via_search(page=page, timeout_ms=timeout_ms, wait_ms=wait_ms)
            search_capture = self._capture(page=page, output_dir=output_dir, stamp=stamp, label="web-search")
            yield {
                "event_type": "web_search_started",
                "title": "Open search engine and search Gmail",
                "detail": "Search query: gmail",
                "data": {"query": "gmail", "url": search_capture["url"], **self._cursor_payload(page=page, x=96, y=84)},
                "snapshot_ref": search_capture["snapshot_ref"],
            }
            yield {
                "event_type": "browser_open",
                "title": "Open browser desktop session",
                "detail": search_capture["url"] or "Search page opened",
                "data": {
                    "url": search_capture["url"],
                    "title": search_capture["title"],
                    **self._cursor_payload(page=page, x=96, y=84),
                },
                "snapshot_ref": search_capture["snapshot_ref"],
            }

            mail_capture = self._capture(page=page, output_dir=output_dir, stamp=stamp, label="gmail-open")
            yield {
                "event_type": "browser_navigate",
                "title": "Open Gmail workspace",
                "detail": mail_capture["url"] or "mail.google.com",
                "data": {
                    "url": mail_capture["url"],
                    "title": mail_capture["title"],
                    **self._cursor_payload(page=page, x=134, y=96),
                },
                "snapshot_ref": mail_capture["snapshot_ref"],
            }

            if self._looks_like_login(page=page):
                auth_capture = self._capture(
                    page=page, output_dir=output_dir, stamp=stamp, label="gmail-auth-required"
                )
                yield {
                    "event_type": "email_auth_required",
                    "title": "Gmail sign-in required",
                    "detail": "Sign in once in the Playwright Gmail profile, then retry.",
                    "data": {"url": auth_capture["url"], "title": auth_capture["title"]},
                    "snapshot_ref": auth_capture["snapshot_ref"],
                }
                context.close()
                raise ConnectorError(
                    "Gmail web login is required for live desktop mode. "
                    "Open Gmail once with this profile and sign in."
                )

            self._ensure_compose_open(page=page, timeout_ms=timeout_ms, wait_ms=wait_ms)
            compose_capture = self._capture(page=page, output_dir=output_dir, stamp=stamp, label="compose-open")
            yield {
                "event_type": "email_open_compose",
                "title": "Open Gmail compose window",
                "detail": "Composer is ready",
                "data": {"url": compose_capture["url"]},
                "snapshot_ref": compose_capture["snapshot_ref"],
            }

            to_field = self._first_visible(
                page=page,
                selectors=[
                    "textarea[name='to']",
                    "input[aria-label='To recipients']",
                    "input[aria-label*='To']",
                ],
            )
            if to_field is None:
                context.close()
                raise ConnectorError("Gmail recipient field not found in compose window.")
            to_cursor = self._move_to_locator(page=page, locator=to_field, timeout_ms=timeout_ms)
            to_field.click(timeout=timeout_ms)
            to_field.fill(to_text, timeout=timeout_ms)
            page.keyboard.press("Tab")
            page.wait_for_timeout(max(300, wait_ms // 2))
            to_capture = self._capture(page=page, output_dir=output_dir, stamp=stamp, label="set-to")
            yield {
                "event_type": "email_set_to",
                "title": "Set recipient",
                "detail": to_text,
                "data": {"recipient": to_text, **to_cursor},
                "snapshot_ref": to_capture["snapshot_ref"],
            }

            subject_field = self._first_visible(
                page=page,
                selectors=["input[name='subjectbox']", "input[aria-label='Subject']"],
            )
            if subject_field is None:
                context.close()
                raise ConnectorError("Gmail subject field not found in compose window.")
            subject_cursor = self._move_to_locator(page=page, locator=subject_field, timeout_ms=timeout_ms)
            subject_field.click(timeout=timeout_ms)
            subject_field.fill(str(subject or "").strip(), timeout=timeout_ms)
            page.wait_for_timeout(max(200, wait_ms // 3))
            subject_capture = self._capture(
                page=page, output_dir=output_dir, stamp=stamp, label="set-subject"
            )
            yield {
                "event_type": "email_set_subject",
                "title": "Set email subject",
                "detail": str(subject or "").strip(),
                "data": {"subject": str(subject or "").strip(), **subject_cursor},
                "snapshot_ref": subject_capture["snapshot_ref"],
            }

            body_field = self._first_visible(
                page=page,
                selectors=[
                    "div[aria-label='Message Body']",
                    "div[role='textbox'][aria-label='Message Body']",
                    "div[role='textbox'][g_editable='true']",
                ],
            )
            if body_field is None:
                context.close()
                raise ConnectorError("Gmail message body field not found in compose window.")
            body_cursor = self._move_to_locator(page=page, locator=body_field, timeout_ms=timeout_ms)
            body_field.click(timeout=timeout_ms)
            text = str(body or "").strip()
            chunks = [text[idx : idx + 120] for idx in range(0, len(text), 120)] or [""]
            typed_preview = ""
            for index, chunk in enumerate(chunks, start=1):
                page.keyboard.type(chunk, delay=8)
                page.wait_for_timeout(max(150, wait_ms // 6))
                typed_preview += chunk
                body_capture = self._capture(
                    page=page, output_dir=output_dir, stamp=stamp, label=f"type-body-{index}"
                )
                yield {
                    "event_type": "email_type_body",
                    "title": f"Type email body {index}/{len(chunks)}",
                    "detail": chunk,
                    "data": {
                        "chunk_index": index,
                        "chunk_total": len(chunks),
                        "typed_preview": typed_preview,
                        **body_cursor,
                    },
                    "snapshot_ref": body_capture["snapshot_ref"],
                }

            body_done_capture = self._capture(
                page=page, output_dir=output_dir, stamp=stamp, label="set-body"
            )
            yield {
                "event_type": "email_set_body",
                "title": "Compose email body",
                "detail": f"{len(text)} characters",
                "data": {"typed_preview": typed_preview or text, **body_cursor},
                "snapshot_ref": body_done_capture["snapshot_ref"],
            }

            if send:
                ready_capture = self._capture(
                    page=page, output_dir=output_dir, stamp=stamp, label="ready-send"
                )
                yield {
                    "event_type": "email_ready_to_send",
                    "title": "Ready to send from Gmail",
                    "detail": "Preparing send click",
                    "data": {"recipient": to_text, **body_cursor},
                    "snapshot_ref": ready_capture["snapshot_ref"],
                }
                send_button = self._first_visible(
                    page=page,
                    selectors=[
                        "div[role='button'][data-tooltip^='Send']",
                        "div[role='button'][aria-label*='Send']",
                        "button:has-text('Send')",
                    ],
                )
                if send_button is None:
                    context.close()
                    raise ConnectorError("Gmail Send button not found in compose window.")
                send_cursor = self._move_to_locator(page=page, locator=send_button, timeout_ms=timeout_ms)
                send_button.click(timeout=timeout_ms)
                page.wait_for_timeout(max(800, wait_ms))
                click_capture = self._capture(
                    page=page, output_dir=output_dir, stamp=stamp, label="click-send"
                )
                yield {
                    "event_type": "email_click_send",
                    "title": "Click Gmail Send",
                    "detail": "Submitting message",
                    "data": {"recipient": to_text, **send_cursor},
                    "snapshot_ref": click_capture["snapshot_ref"],
                }
                sent_capture = self._capture(
                    page=page, output_dir=output_dir, stamp=stamp, label="sent"
                )
                yield {
                    "event_type": "email_sent",
                    "title": "Gmail message sent",
                    "detail": to_text,
                    "data": {"recipient": to_text, **send_cursor},
                    "snapshot_ref": sent_capture["snapshot_ref"],
                }
                result = {
                    "mode": "playwright_desktop",
                    "status": "sent",
                    "url": sent_capture["url"],
                    "snapshot_ref": sent_capture["snapshot_ref"],
                }
            else:
                page.wait_for_timeout(max(1000, wait_ms))
                ready_capture = self._capture(
                    page=page, output_dir=output_dir, stamp=stamp, label="draft-ready"
                )
                yield {
                    "event_type": "email_ready_to_send",
                    "title": "Draft ready in Gmail compose",
                    "detail": "Draft preserved in mailbox",
                    "data": {"recipient": to_text},
                    "snapshot_ref": ready_capture["snapshot_ref"],
                }
                result = {
                    "mode": "playwright_desktop",
                    "status": "draft_saved",
                    "url": ready_capture["url"],
                    "snapshot_ref": ready_capture["snapshot_ref"],
                }
            context.close()
            return result
