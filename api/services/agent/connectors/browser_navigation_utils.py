from __future__ import annotations

import random
import re
from typing import Any
from urllib.parse import urljoin, urlparse


def extract_same_origin_links(
    *,
    page: Any,
    origin_url: str,
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []
    parsed_origin = urlparse(origin_url)
    origin_host = (parsed_origin.hostname or "").lower()
    if not origin_host:
        return []

    hrefs: list[str] = page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]'))
            .map((element) => element.getAttribute('href') || '')
            .filter(Boolean)
        """
    )
    targets: list[str] = []
    seen: set[str] = {origin_url}
    for href in hrefs:
        candidate = urljoin(origin_url, str(href))
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"}:
            continue
        host = (parsed.hostname or "").lower()
        if host != origin_host:
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized in seen:
            continue
        seen.add(normalized)
        targets.append(normalized)
        if len(targets) >= limit:
            break
    return targets


def _cursor_payload_for_target(*, page: Any, target: Any) -> dict[str, float]:
    try:
        box = target.bounding_box()
    except Exception:
        box = None
    if not isinstance(box, dict):
        return {}
    try:
        center_x = float(box.get("x", 0.0)) + (float(box.get("width", 0.0)) / 2.0)
        center_y = float(box.get("y", 0.0)) + min(18.0, float(box.get("height", 0.0)) / 2.0)
    except Exception:
        return {}
    try:
        page.mouse.move(center_x, center_y, steps=random.randint(8, 18))
    except Exception:
        pass
    try:
        viewport = page.viewport_size or {"width": 1366, "height": 768}
        width = max(1.0, float(viewport.get("width") or 1366.0))
        height = max(1.0, float(viewport.get("height") or 768.0))
        return {
            "cursor_x": round((center_x / width) * 100.0, 2),
            "cursor_y": round((center_y / height) * 100.0, 2),
        }
    except Exception:
        return {}


def accept_cookie_banner(*, page: Any, wait_ms: int = 1200) -> dict[str, Any]:
    selectors = [
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
        ".ot-sdk-container #onetrust-accept-btn-handler",
        "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button[aria-label*='Accept all' i]",
        "button[aria-label*='Allow all' i]",
        "button[data-testid*='accept' i]",
        "button[data-cookiebanner='accept']",
        "button[data-qa='accept-all-cookies']",
        "button[id*='accept' i][id*='cookie' i]",
        "button[class*='accept' i][class*='cookie' i]",
        "#cookie-accept-all",
        ".cookie-accept-all",
        ".cc-allow",
        "button:has-text('ALLOW ALL COOKIES')",
        "button:has-text('Allow all cookies')",
        "button:has-text('Accept all cookies')",
        "button:has-text('Accept cookies')",
        "button:has-text('Accept all')",
        "button:has-text('Allow all')",
        "button:has-text('Allow all and continue')",
        "button:has-text('Agree and continue')",
        "button:has-text('Accept')",
        "button:has-text('I agree')",
        "button:has-text('Got it')",
        "button:has-text('Tout accepter')",
        "button:has-text('Accepter')",
        "button:has-text('Akzeptieren')",
        "button:has-text('Alle akzeptieren')",
        "button:has-text('Accepteer')",
        "button:has-text('Alle cookies toestaan')",
        "button:has-text('Aceptar todo')",
        "button:has-text('Aceptar cookies')",
        "a:has-text('Accept all')",
        "a:has-text('Allow all')",
        "a:has-text('Accept')",
    ]
    label_regex = re.compile(
        r"(accept|allow|agree|consent|accepter|akzeptieren|accepteer|toestaan|aceptar|tout accepter)",
        re.IGNORECASE,
    )

    def _try_click(locator: Any, label: str) -> dict[str, Any]:
        try:
            if hasattr(locator, "count"):
                if locator.count() <= 0:
                    return {}
                candidate = locator.first
            else:
                candidate = locator
            if hasattr(candidate, "is_visible") and not candidate.is_visible():
                return {}
            cursor_payload = _cursor_payload_for_target(page=page, target=candidate)
            candidate.click(timeout=2000)
            page.wait_for_timeout(max(120, min(800, wait_ms)))
            return {"accepted": True, "label": label, **cursor_payload}
        except Exception:
            return {}

    for selector in selectors:
        accepted = _try_click(page.locator(selector), selector)
        if accepted:
            return accepted

    frames = [page.main_frame] + list(page.frames)
    for frame in frames:
        try:
            buttons = frame.get_by_role("button")
            total = min(buttons.count(), 40)
        except Exception:
            continue
        for index in range(total):
            try:
                button = buttons.nth(index)
                text = str(button.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
            if not text or not label_regex.search(text):
                continue
            accepted = _try_click(button, text)
            if accepted:
                return accepted
        try:
            links = frame.get_by_role("link")
            link_total = min(links.count(), 20)
        except Exception:
            link_total = 0
            links = None
        for index in range(link_total):
            try:
                link = links.nth(index) if links is not None else None
                text = str(link.inner_text(timeout=300) or "").strip() if link is not None else ""
            except Exception:
                continue
            if not text or not label_regex.search(text):
                continue
            accepted = _try_click(link, text) if link is not None else {}
            if accepted:
                return accepted
        try:
            submit_inputs = frame.locator("input[type='submit'], input[type='button']")
            input_total = min(submit_inputs.count(), 20)
        except Exception:
            input_total = 0
            submit_inputs = None
        for index in range(input_total):
            try:
                item = submit_inputs.nth(index) if submit_inputs is not None else None
                text = str(item.get_attribute("value") or "").strip() if item is not None else ""
            except Exception:
                continue
            if not text or not label_regex.search(text):
                continue
            accepted = _try_click(item, text) if item is not None else {}
            if accepted:
                return accepted

    return {"accepted": False}
