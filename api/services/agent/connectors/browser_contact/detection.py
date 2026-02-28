from __future__ import annotations

from typing import Any


def first_visible(scope: Any, selectors: list[str]) -> Any | None:
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


def locate_contact_form(page: Any, *, wait_ms: int) -> tuple[Any | None, bool]:
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

    contact_link = first_visible(
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
