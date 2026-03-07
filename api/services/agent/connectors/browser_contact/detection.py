from __future__ import annotations

from pathlib import Path
from typing import Any

from .contact_discovery import locate_contact_form_with_discovery


def first_visible(scope: Any, selectors: list[str]) -> Any | None:
    for selector in selectors:
        try:
            locator = scope.locator(selector)
            if locator.count() <= 0:
                continue
            candidate = locator.first
            if hasattr(candidate, "is_visible") and not candidate.is_visible():
                continue
            return candidate
        except Exception:
            continue
    return None


def locate_contact_form(
    page: Any,
    *,
    wait_ms: int,
    timeout_ms: int = 12000,
    max_hops: int = 5,
    goal_page_discovery_enabled: bool = False,
    goal_page_discovery_decision: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    stamp_prefix: str = "",
) -> tuple[Any | None, bool, list[dict[str, Any]]]:
    return locate_contact_form_with_discovery(
        page,
        wait_ms=wait_ms,
        timeout_ms=timeout_ms,
        max_hops=max_hops,
        goal_page_discovery_enabled=goal_page_discovery_enabled,
        goal_page_discovery_decision=goal_page_discovery_decision,
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
