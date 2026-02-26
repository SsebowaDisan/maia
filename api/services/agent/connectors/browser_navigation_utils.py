from __future__ import annotations

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


def accept_cookie_banner(*, page: Any, wait_ms: int = 1200) -> dict[str, Any]:
    selectors = [
        "#onetrust-accept-btn-handler",
        "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button:has-text('ALLOW ALL COOKIES')",
        "button:has-text('Allow all cookies')",
        "button:has-text('Accept all cookies')",
        "button:has-text('Accept all')",
        "button:has-text('Allow all')",
        "button:has-text('I agree')",
        "button:has-text('Tout accepter')",
        "button:has-text('Accepter')",
        "button:has-text('Akzeptieren')",
        "button:has-text('Accepteer')",
        "button:has-text('Alle cookies toestaan')",
        "button:has-text('Aceptar todo')",
    ]
    label_regex = re.compile(
        r"(accept|allow|agree|consent|accepter|akzeptieren|accepteer|toestaan|aceptar|tout accepter)",
        re.IGNORECASE,
    )

    def _try_click(locator: Any, label: str) -> bool:
        try:
            if locator.count() <= 0:
                return False
            candidate = locator.first
            if hasattr(candidate, "is_visible") and not candidate.is_visible():
                return False
            candidate.click(timeout=2000)
            page.wait_for_timeout(max(120, min(800, wait_ms)))
            return True
        except Exception:
            return False

    for selector in selectors:
        if _try_click(page.locator(selector), selector):
            return {"accepted": True, "label": selector}

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
            if _try_click(button, text):
                return {"accepted": True, "label": text}

    return {"accepted": False}
